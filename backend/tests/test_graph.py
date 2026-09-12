"""Phase 4 tests — Neo4j graph (fake-driver unit tests, stdlib unittest).

No live Neo4j required: FakeDriver emulates MERGE semantics, counters,
traversal and search over the exact Cypher shapes the builder/queries emit.
Live-database coverage lives in test_neo4j_integration.py (marked, opt-in).
"""

import contextlib
import json
import os
import re
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.documents import DocumentStore  # noqa: E402
from app.database.neo4j import (  # noqa: E402
    Neo4jConfig,
    Neo4jConfigError,
    Neo4jService,
    Neo4jUnavailable,
)
from app.services import graph_builder as gb  # noqa: E402
from app.services import graph_queries as gq  # noqa: E402
from app.services.entity_resolution import resolve_document  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402
from app.services.validation import IngestionError  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:
    HAS_API = False


# ---------------------------------------------------------------------------
# Fake driver: same run()/summary() protocol, in-memory MERGE semantics.
# ---------------------------------------------------------------------------

class FakeCounters:
    def __init__(self, nodes_created=0, relationships_created=0):
        self.nodes_created = nodes_created
        self.relationships_created = relationships_created


class FakeSummary:
    def __init__(self, nodes_created=0, relationships_created=0):
        self.counters = FakeCounters(nodes_created, relationships_created)


class FakeResult(list):
    def __init__(self, rows, nodes_created=0, relationships_created=0):
        super().__init__(rows)
        self._summary = FakeSummary(nodes_created, relationships_created)

    def consume(self):
        # Mirrors neo4j driver v5 Result.consume() -> summary.
        return self._summary


class FakeSession:
    def __init__(self, store, calls):
        self.nodes = store["nodes"]  # (label, id) -> props
        self.edges = store["edges"]  # (src, type, dst, eid) -> record
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _node_dict(self, label, node_id):
        return {"_labels": [label], **self.nodes[(label, node_id)]}

    # -- statement dispatch on the builder/query Cypher shapes --------------
    def run(self, cypher, params=None, timeout=None):
        params = params or {}
        self.calls.append((cypher, dict(params)))
        if cypher.startswith("CREATE CONSTRAINT") or \
                cypher.startswith("CREATE INDEX"):
            return FakeResult([])
        if cypher.startswith("MATCH p = "):
            return self._traverse(cypher, params)
        if "n.name CONTAINS" in cypher:
            return self._search(params)
        if "WHERE n.id IN" in cypher:
            return FakeResult([{"id": i} for i in params["ids"]
                               if self._find(i) is not None])
        if cypher.startswith("MATCH ()-[r {id:"):
            eid = params["eid"]
            found = [k for k in self.edges if k[3] == eid]
            return FakeResult([{"id": eid}] if found else [])
        if cypher.startswith("MATCH (n) RETURN n LIMIT"):
            limit = params.get("limit", 2001)
            rows = [{"n": self._node_dict(label, nid)}
                    for label, nid in sorted(self.nodes)[:limit]]
            return FakeResult(rows)
        if cypher.startswith("MATCH (a)-[r]->(b) RETURN"):
            limit = params.get("limit", 5001)
            rows = [{"src": src, "r": dict(edge), "dst": dst}
                    for (src, _, dst, _), edge in
                    sorted(self.edges.items())[:limit]]
            return FakeResult(rows)
        if cypher.startswith("MATCH (n {id: $id})"):
            hit = self._find(params["id"])
            if hit is None:
                return FakeResult([])
            label, node_id = hit
            return FakeResult([{"n": self._node_dict(label, node_id)}])
        if "MERGE (a)-[r:" in cypher:
            return self._merge_edge(cypher, params)
        if cypher.startswith("MERGE (n:"):
            return self._merge_node(cypher, params)
        raise AssertionError(f"fake cannot handle cypher: {cypher[:80]}")

    def _find(self, node_id):
        for label, nid in self.nodes:
            if nid == node_id:
                return label, nid
        return None

    def _merge_node(self, cypher, params):
        label = re.match(r"MERGE \(n:(\w+)", cypher).group(1)
        key = (label, params["id"])
        created = key not in self.nodes
        if created:
            props = dict(params["props"])
            props["id"] = params["id"]
            self.nodes[key] = props
        # First-write-wins (mirrors the real MERGE): re-merges are no-ops.
        return FakeResult([], nodes_created=1 if created else 0)

    def _merge_edge(self, cypher, params):
        rel = re.search(r"MERGE \(a\)-\[r:(\w+)", cypher).group(1)
        key = (params["src_id"], rel, params["dst_id"], params["edge_id"])
        created = key not in self.edges
        if created:
            self.edges[key] = {"id": params["edge_id"], "type": rel,
                               "source": params["src_id"],
                               "target": params["dst_id"],
                               "props": dict(params["props"])}
        return FakeResult([], relationships_created=1 if created else 0)

    def _search(self, params):
        query, label, skip, limit = (params["q"], params["label"],
                                     params["skip"], params["limit"])
        hits = []
        for (node_label, _), props in self.nodes.items():
            if label is not None and node_label != label:
                continue
            hay = [str(props.get(f, ""))
                   for f in ("name", "normalized_name", "number",
                             "registration_number", "account_number")]
            if any(query in field for field in hay):
                hits.append({"n": self._node_dict(node_label, props["id"])})
        return FakeResult(hits[skip:skip + limit])

    def _neighbors(self, node_id):
        out = []
        for (src, rtype, dst, _), edge in self.edges.items():
            if src == node_id:
                out.append((rtype, dst, edge))
            elif dst == node_id:
                out.append((rtype, src, edge))
        return out

    def _traverse(self, cypher, params):
        depth = int(re.search(r"\[\*1\.\.(\d)\]", cypher).group(1))
        rel_types = params.get("rel_types") or []
        node_labels = params.get("node_labels") or []
        center = params["id"]
        if self._find(center) is None:
            return FakeResult([])
        rows = []
        # BFS paths; one row per path.
        queue = [(center, [center], [])]
        seen_depth = {center: 0}
        while queue:
            current, path_nodes, path_edges = queue.pop(0)
            current_depth = len(path_edges)
            if current_depth >= depth:
                continue
            for rtype, other, edge in self._neighbors(current):
                if rel_types and rtype not in rel_types:
                    continue
                label, _ = self._find(other)
                if node_labels and label not in node_labels:
                    continue
                if other in path_nodes:
                    continue
                new_nodes = path_nodes + [other]
                new_edges = path_edges + [(rtype, edge)]
                label_c, _ = self._find(center)
                ns = [self._node_dict(self._find(n)[0], n)
                      for n in new_nodes]
                _ = label_c
                rs = [{"id": e["id"], "type": rt, "source": s, "target": t,
                       "props": dict(e["props"])}
                      for rt, e, (s, t) in
                      [(r, ed, (new_nodes[i], new_nodes[i + 1]))
                       for i, (r, ed) in enumerate(new_edges)]]
                rows.append({"ns": ns, "rs": rs})
                if other not in seen_depth:
                    seen_depth[other] = current_depth + 1
                    queue.append((other, new_nodes, new_edges))
        limit = params.get("row_limit", 301)
        return FakeResult(rows[:limit])

    def close(self):
        pass


class FakeDriver:
    def __init__(self, fail_verify=False):
        self.store = {"nodes": {}, "edges": {}}
        self.calls = []
        self.fail_verify = fail_verify

    def session(self, database=None):
        return FakeSession(self.store, self.calls)

    def verify_connectivity(self):
        if self.fail_verify:
            raise OSError("connection refused")

    def close(self):
        pass


def fake_service(driver=None):
    driver = driver if driver is not None else FakeDriver()
    config = Neo4jConfig(uri="bolt://fake:7687", username="neo4j",
                         password="fake", database="neo4j")
    return Neo4jService(config, driver=driver), driver


def fresh_store(tmpdir):
    return DocumentStore(os.path.join(tmpdir, "docs.db"))


# ---------------------------------------------------------------------------
# Config / connection
# ---------------------------------------------------------------------------

class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = Neo4jConfig.from_env({"NEO4J_PASSWORD": "pw"})
        self.assertEqual(config.uri, "bolt://localhost:7687")
        self.assertEqual(config.username, "neo4j")
        self.assertEqual(config.database, "neo4j")

    def test_env_overrides(self):
        config = Neo4jConfig.from_env({
            "NEO4J_URI": "bolt://db:7687", "NEO4J_USERNAME": "analyst",
            "NEO4J_PASSWORD": "pw", "NEO4J_DATABASE": "crime"})
        self.assertEqual((config.uri, config.username, config.database),
                         ("bolt://db:7687", "analyst", "crime"))

    def test_legacy_user_var_and_bolt_port(self):
        config = Neo4jConfig.from_env(
            {"NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "pw",
             "NEO4J_BOLT_PORT": "7688"})
        self.assertEqual(config.uri, "bolt://localhost:7688")

    def test_missing_password_is_structured(self):
        with self.assertRaises(Neo4jConfigError) as ctx:
            Neo4jConfig.from_env({})
        self.assertEqual(ctx.exception.http_status, 500)
        self.assertIn("NEO4J_PASSWORD", str(ctx.exception))

    def test_describe_hides_password(self):
        config = Neo4jConfig.from_env({"NEO4J_PASSWORD": "s3cret"})
        described = json.dumps(config.describe())
        self.assertNotIn("s3cret", described)

    def test_verify_failure_is_503(self):
        service, _ = fake_service(FakeDriver(fail_verify=True))
        with self.assertRaises(Neo4jUnavailable) as ctx:
            service.verify()
        self.assertEqual(ctx.exception.http_status, 503)

    def test_verify_ok(self):
        service, _ = fake_service()
        self.assertTrue(service.verify()["ok"])


# ---------------------------------------------------------------------------
# Builder unit tests (fake sessions)
# ---------------------------------------------------------------------------

class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.session = FakeSession(self.driver.store, self.driver.calls)

    def person(self, pid="person_001", name="Rahul Sharma"):
        return {"label": "Person",
                "props": {"id": pid, "name": name,
                          "normalized_name": name.lower(), "risk_score": 0.0}}

    def test_node_create_then_existing(self):
        self.assertTrue(gb.merge_node(self.session, "Person",
                                      self.person()["props"]))
        self.assertFalse(gb.merge_node(self.session, "Person",
                                       self.person()["props"]))

    def test_duplicate_prevention_same_id(self):
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Person",
                      {"id": "person_001", "name": "Someone Else",
                       "normalized_name": "someone else", "risk_score": 0.0})
        self.assertEqual(len(self.driver.store["nodes"]), 1)

    def test_relationship_create_then_existing(self):
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Person",
                      self.person("person_002", "Amit Kumar")["props"])
        eid = gb.edge_id("person_001", "CALLED", "person_002", "CDR_001")
        self.assertTrue(gb.merge_relationship(
            self.session, "Person", "person_001", "CALLED", "Person",
            "person_002", eid, {"source_record_id": "CDR_001"}))
        self.assertFalse(gb.merge_relationship(
            self.session, "Person", "person_001", "CALLED", "Person",
            "person_002", eid, {"source_record_id": "CDR_001"}))

    def test_distinct_events_preserved(self):
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Person",
                      self.person("person_002", "Amit Kumar")["props"])
        for cdr in ("CDR_001", "CDR_002"):
            gb.merge_relationship(
                self.session, "Person", "person_001", "CALLED", "Person",
                "person_002", gb.edge_id("person_001", "CALLED",
                                         "person_002", cdr),
                {"source_record_id": cdr})
        self.assertEqual(len(self.driver.store["edges"]), 2)

    def test_unsupported_relationship_rejected(self):
        before = len(self.driver.calls)
        with self.assertRaises(IngestionError) as ctx:
            gb.merge_relationship(
                self.session, "Person", "a", "FRIENDS_WITH", "Person", "b",
                "rel_x", {})
        self.assertEqual(ctx.exception.http_status, 422)
        self.assertEqual(len(self.driver.calls), before)

    def test_uses_alias_converges_to_used(self):
        self.assertEqual(gb.normalize_rel_type("USES"), "USED")
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Phone",
                      {"id": "phone_001", "number": "+919876543210"})
        eid = gb.edge_id("person_001", "USED", "phone_001", "S1")
        gb.merge_relationship(self.session, "Person", "person_001", "USES",
                              "Phone", "phone_001", eid, {})
        key = ("person_001", "USED", "phone_001", eid)
        self.assertIn(key, self.driver.store["edges"])

    def test_cypher_is_parameterized(self):
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Phone",
                      {"id": "phone_001", "number": "+919876543210"})
        gb.merge_relationship(
            self.session, "Person", "person_001", "CALLED", "Phone",
            "phone_001", "rel_1", {"confidence": 0.9})
        for cypher, _ in self.driver.calls:
            for literal in ("Rahul Sharma", "+919876543210", "person_001"):
                self.assertNotIn(literal, cypher)
            if cypher.startswith("MERGE"):
                self.assertIn("$", cypher)

    def test_provenance_and_confidence_preserved(self):
        gb.merge_node(self.session, "Person", self.person()["props"])
        gb.merge_node(self.session, "Person",
                      self.person("person_002", "Amit Kumar")["props"])
        props = {"timestamp": "2026-08-12T10:32:00Z", "duration": 420,
                 "confidence": 0.96, "source_record_id": "CDR_001"}
        gb.merge_relationship(
            self.session, "Person", "person_001", "CALLED", "Person",
            "person_002", gb.edge_id("person_001", "CALLED", "person_002",
                                     "CDR_001"), props)
        stored = list(self.driver.store["edges"].values())[0]["props"]
        for key, value in props.items():
            self.assertEqual(stored[key], value)

    def test_schema_ddl_names(self):
        gb.ensure_schema(self.session)
        ddl = [c for c, _ in self.driver.calls]
        for name in ("person_id_unique", "bankaccount_id_unique",
                     "fir_id_unique"):
            self.assertTrue(any(name in stmt for stmt in ddl), name)
        self.assertEqual(sum("CREATE CONSTRAINT" in s for s in ddl), 8)
        self.assertEqual(sum("CREATE INDEX" in s for s in ddl), 6)

    def test_entity_label_mapping(self):
        self.assertEqual(gb.ENTITY_LABEL["PERSON"], "Person")
        self.assertEqual(gb.ENTITY_LABEL["ACCOUNT"], "BankAccount")
        self.assertEqual(gb.ENTITY_LABEL["FIR"], "FIR")
        with self.assertRaises(IngestionError):
            gb.merge_node(self.session, "Criminal", {"id": "x"})

    def test_edge_id_deterministic(self):
        first = gb.edge_id("a", "CALLED", "b", "CDR_1")
        self.assertEqual(first, gb.edge_id("a", "CALLED", "b", "CDR_1"))
        self.assertNotEqual(first, gb.edge_id("a", "CALLED", "b", "CDR_2"))

    def test_write_graph_counts_and_verification(self):
        nodes = [self.person(),
                 {"label": "Phone",
                  "props": {"id": "phone_001", "number": "+919876543210"}}]
        rels = [{"source_label": "Person", "source_id": "person_001",
                 "type": "USED", "target_label": "Phone",
                 "target_id": "phone_001",
                 "edge_id": gb.edge_id("person_001", "USED", "phone_001",
                                       "S1"),
                 "props": {"source_record_id": "S1"}}]
        counts = gb.write_graph(self.session, nodes, rels)
        self.assertEqual((counts["nodes_created"],
                          counts["relationships_created"]), (2, 1))
        again = gb.write_graph(self.session, nodes, rels)
        self.assertEqual((again["nodes_created"],
                          again["relationships_created"]), (0, 0))
        self.assertEqual((again["nodes_existing"],
                          again["relationships_existing"]), (2, 1))
        verification = gb.verify_graph(
            self.session, ["person_001", "phone_001"],
            [rels[0]["edge_id"]])
        self.assertTrue(verification["verified"])
        missing = gb.verify_graph(self.session, ["ghost"], ["rel_ghost"])
        self.assertFalse(missing["verified"])
        self.assertEqual(missing["missing_nodes"], ["ghost"])


# ---------------------------------------------------------------------------
# Composition: structured records -> nodes/relationships (no invention)
# ---------------------------------------------------------------------------

class BuildFromUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raw = os.path.join(self.tmp.name, "raw")
        processed = os.path.join(self.tmp.name, "processed")
        self.store = fresh_store(self.tmp.name)
        self.svc = IngestionService(self.store, raw, processed)

    def tearDown(self):
        self.tmp.cleanup()

    def _compose(self, content: bytes, filename: str, dtype: str):
        doc = self.svc.upload(content, filename, dtype)
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "SUCCEEDED")
        path = os.path.join(self.tmp.name, "processed", doc["id"],
                            "records.json")
        with open(path, encoding="utf-8") as fh:
            records = json.load(fh)
        return gb.build_from_upload(self.store, doc["id"], records)

    def _labels(self, nodes):
        return {(n["label"], n["props"]["id"]) for n in nodes}

    def test_fir_creates_fir_node_and_mentioned_in(self):
        nodes, rels, _ = self._compose(
            b"fir_id,date,police_station,text,source\n"
            b"FIR_001,2026-03-20,Shanti Nagar Police Station,"
            b"Rahul Sharma visited Delhi.,SYNTHETIC\n",
            "fir.csv", "FIR")
        self.assertIn(("FIR", "FIR_001"), self._labels(nodes))
        mentioned = [r for r in rels if r["type"] == "MENTIONED_IN"]
        self.assertTrue(all(r["target_id"] == "FIR_001" for r in mentioned))
        self.assertGreaterEqual(len(mentioned), 1)
        # Co-occurrence alone creates no person-person edge.
        person_edges = [r for r in rels if r["type"] in ("CALLED", "MET")]
        self.assertEqual(person_edges, [])

    def test_cdr_creates_called_edges(self):
        resolve_document(self.store, "SEED", [
            {"id": "temp_001", "type": "PERSON", "value": "Rahul Sharma",
             "confidence": 0.9, "normalized_value": "rahul sharma",
             "method": "seed"},
            {"id": "temp_002", "type": "PHONE", "value": "+919876543210",
             "confidence": 1.0, "normalized_value": "+919876543210",
             "method": "seed"}])
        person = self.store.find_entities_by_normalized(
            "PERSON", "rahul sharma")[0]
        self.store.update_entity_attrs(
            person["id"], {"phones": ["+919876543210"], "accounts": [],
                           "vehicles": [], "organizations": []})
        nodes, rels, _ = self._compose(
            b"cdr_id,caller,receiver,timestamp,duration\n"
            b"CDR_001,+919876543210,+919876549999,2026-08-12T10:32:00Z,420\n",
            "cdr.csv", "CDR")
        phone_edges = [r for r in rels if r["type"] == "CALLED"
                       and r["source_label"] == "Phone"]
        self.assertEqual(len(phone_edges), 1)
        self.assertEqual(phone_edges[0]["props"]["source_record_id"],
                         "CDR_001")

    def test_transaction_creates_transferred_to(self):
        nodes, rels, _ = self._compose(
            b"transaction_id,sender_account,receiver_account,amount,"
            b"currency,timestamp\n"
            b"TXN001,ACC001,ACC002,75000,INR,2026-08-12T13:40:00Z\n",
            "txn.csv", "TRANSACTION")
        edges = [r for r in rels if r["type"] == "TRANSFERRED_TO"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["props"]["amount"], 75000)
        self.assertIn(("BankAccount", edges[0]["source_id"]),
                      self._labels(nodes))

    def test_vehicle_creates_used_and_owns(self):
        nodes, rels, _ = self._compose(
            b"vehicle_id,registration_number,owner_name,source\n"
            b"vehicle_001,DL01AB1234,Rahul Sharma,SYNTHETIC\n",
            "veh.csv", "VEHICLE")
        types = {r["type"] for r in rels}
        self.assertIn("USED", types)
        self.assertIn("OWNS", types)

    def test_location_creates_node_only(self):
        nodes, rels, _ = self._compose(
            b"location_id,name,latitude,longitude\n"
            b"location_001,Shanti Nagar Delhi,28.61,77.20\n",
            "loc.csv", "LOCATION")
        self.assertEqual(len(rels), 0)
        self.assertIn(("Location", "location_001"), self._labels(nodes))

    def test_repeated_compose_is_stable(self):
        content = (b"transaction_id,sender_account,receiver_account,amount,"
                   b"currency,timestamp\n"
                   b"TXN001,ACC001,ACC002,75000,INR,2026-08-12T13:40:00Z\n")
        doc = self.svc.upload(content, "a.csv", "TRANSACTION")
        self.assertEqual(self.svc.process(doc["id"])["status"], "SUCCEEDED")
        path = os.path.join(self.tmp.name, "processed", doc["id"],
                            "records.json")
        with open(path, encoding="utf-8") as fh:
            records = json.load(fh)
        first = gb.build_from_upload(self.store, doc["id"], records)
        second = gb.build_from_upload(self.store, doc["id"], records)
        self.assertEqual(
            sorted(r["edge_id"] for r in first[1]),
            sorted(r["edge_id"] for r in second[1]))
        self.assertEqual(
            sorted(r["edge_id"] for r in first[1]),
            sorted(r["edge_id"] for r in second[1]))


# ---------------------------------------------------------------------------
# Query service (fake sessions)
# ---------------------------------------------------------------------------

class QueryTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.session = FakeSession(self.driver.store, self.driver.calls)
        gb.merge_node(self.session, "Person",
                      {"id": "person_001", "name": "Rahul Sharma",
                       "normalized_name": "rahul sharma", "risk_score": 0.0})
        gb.merge_node(self.session, "Person",
                      {"id": "person_002", "name": "Amit Kumar",
                       "normalized_name": "amit kumar", "risk_score": 0.0})
        gb.merge_node(self.session, "Phone",
                      {"id": "phone_001", "number": "+919876543210"})
        gb.merge_node(self.session, "Location",
                      {"id": "location_001", "name": "Delhi",
                       "latitude": None, "longitude": None})
        gb.merge_relationship(
            self.session, "Person", "person_001", "CALLED", "Person",
            "person_002", "rel_1",
            {"confidence": 0.9, "timestamp": "2026-08-12T10:32:00Z",
             "source_record_id": "CDR_001"})
        gb.merge_relationship(
            self.session, "Person", "person_001", "USED", "Phone",
            "phone_001", "rel_2", {"source_record_id": "S1"})
        gb.merge_relationship(
            self.session, "Person", "person_001", "LOCATED_AT", "Location",
            "location_001", "rel_3", {"source_record_id": "S2"})

    def test_get_entity(self):
        node = gq.get_entity(self.session, "person_001")
        self.assertEqual(node, {"id": "person_001", "label": "Rahul Sharma",
                                "type": "PERSON",
                                "metadata": {"normalized_name": "rahul sharma",
                                             "risk_score": 0.0}})
        self.assertIsNone(gq.get_entity(self.session, "ghost"))
        with self.assertRaises(IngestionError):
            gq.get_entity(self.session, "../evil")

    def test_neighborhood_shape_and_metadata(self):
        data = gq.get_neighborhood(self.session, "person_001")
        self.assertFalse(data["truncated"])
        edge = [e for e in data["edges"] if e["id"] == "rel_1"][0]
        self.assertEqual(edge, {"id": "rel_1", "source": "person_001",
                                "target": "person_002", "type": "CALLED",
                                "metadata": {"confidence": 0.9,
                                             "timestamp": "2026-08-12T10:32:00Z",
                                             "source_record": "CDR_001"}})
        self.assertTrue(all({"id", "label", "type"} <= set(n)
                            for n in data["nodes"]))

    def test_depth_enforced(self):
        with self.assertRaises(IngestionError):
            gq.get_neighborhood(self.session, "person_001", depth=4)
        with self.assertRaises(IngestionError):
            gq.get_neighborhood(self.session, "person_001", depth=0)

    def test_filters(self):
        data = gq.get_neighborhood(self.session, "person_001",
                                   rel_types=["USED"])
        self.assertEqual({e["type"] for e in data["edges"]}, {"USED"})
        data = gq.get_neighborhood(self.session, "person_001",
                                   node_types=["LOCATION"])
        self.assertTrue(all(n["type"] == "LOCATION" or
                            n["id"] == "person_001" for n in data["nodes"]))
        with self.assertRaises(IngestionError):
            gq.get_neighborhood(self.session, "person_001",
                                rel_types=["HACKED"])
        with self.assertRaises(IngestionError):
            gq.get_neighborhood(self.session, "person_001",
                                node_types=["Criminal"])

    def test_limits_truncate(self):
        data = gq.get_neighborhood(self.session, "person_001", limit_nodes=1)
        self.assertLessEqual(len(data["nodes"]), 1)
        self.assertTrue(data["truncated"])

    def test_search(self):
        result = gq.search_entities(self.session, "Rahul")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], "person_001")
        result = gq.search_entities(self.session, "919876543210")
        self.assertEqual(result["items"][0]["type"], "PHONE")
        result = gq.search_entities(self.session, "a", entity_type="LOCATION")
        self.assertTrue(all(i["type"] == "Location" for i in result["items"]))
        with self.assertRaises(IngestionError):
            gq.search_entities(self.session, "")
        with self.assertRaises(IngestionError):
            gq.search_entities(self.session, "x", entity_type="CRIMINAL")


def fresh_store(tmpdir):
    from app.database.documents import DocumentStore

    return DocumentStore(os.path.join(tmpdir, "docs.db"))


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class GraphApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.driver = FakeDriver()
        config = Neo4jConfig(uri="bolt://fake:7687", username="neo4j",
                             password="fake", database="neo4j")
        deps_mod.set_graph_service_override(Neo4jService(config,
                                                         driver=self.driver))
        self.client = make_authed_client(fastapi_app)

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        deps_mod.reset_graph_service()
        self.tmp.cleanup()

    def _session(self):
        return FakeSession(self.driver.store, self.driver.calls)

    def test_entities_empty(self):
        resp = self.client.get("/api/entities")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["pagination"]["total"], 0)

    def test_entities_list_and_detail(self):
        resolve = self.client.post("/api/entities/resolve", json={
            "document_id": "FIR_001",
            "entities": [{"id": "temp_001", "type": "PERSON",
                          "value": "Rahul Sharma", "confidence": 0.9,
                          "normalized_value": "rahul sharma",
                          "method": "test"}]})
        self.assertEqual(resolve.status_code, 200)
        canonical = resolve.json()["data"]["resolved"][0]["canonical_id"]
        listing = self.client.get("/api/entities?type=PERSON&q=rahul")
        items = listing.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["aliases"], [])
        detail = self.client.get(f"/api/entities/{canonical}")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()["data"]
        self.assertEqual(body["name"], "Rahul Sharma")
        self.assertIsNone(body["analytics_summary"])
        self.assertEqual(self.client.get("/api/entities/ghost").status_code,
                         404)
        self.assertEqual(
            self.client.get("/api/entities?type=CRIMINAL").status_code, 422)
        self.assertEqual(
            self.client.get("/api/entities?sort=priority").status_code, 422)

    def test_graph_endpoints_over_fake(self):
        gb.merge_node(self._session(), "Person",
                      {"id": "person_001", "name": "Rahul Sharma",
                       "normalized_name": "rahul sharma", "risk_score": 0.0})
        gb.merge_node(self._session(), "Person",
                      {"id": "person_002", "name": "Amit Kumar",
                       "normalized_name": "amit kumar", "risk_score": 0.0})
        gb.merge_relationship(
            self._session(), "Person", "person_001", "CALLED", "Person",
            "person_002", "rel_1", {"confidence": 0.9})
        resp = self.client.get("/api/graph/person_001")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("truncated", data)
        edge = [e for e in data["edges"] if e["id"] == "rel_1"][0]
        self.assertEqual((edge["source"], edge["target"], edge["type"]),
                         ("person_001", "person_002", "CALLED"))
        neighbors = self.client.get(
            "/api/graph/person_001/neighbors?rel_types=CALLED")
        self.assertEqual(neighbors.status_code, 200)
        self.assertEqual(self.client.get("/api/graph/ghost").status_code,
                         404)
        self.assertEqual(self.client.get("/api/graph/person_001?depth=9")
                         .status_code, 422)

    def test_build_end_to_end_and_idempotent(self):
        with open(os.path.join(REPO_ROOT, "data", "sample", "fir.csv"),
                  "rb") as fh:
            content = fh.read()
        upload = self.client.post(
            "/api/upload", files={"file": ("fir.csv", content, "text/csv")},
            data={"dataset_type": "FIR"}).json()["data"]
        proc = self.client.post("/api/process",
                                json={"upload_id": upload["upload_id"]})
        self.assertEqual(proc.status_code, 200)
        first = self.client.post("/api/graph/build",
                                 json={"upload_id": upload["upload_id"]})
        self.assertEqual(first.status_code, 200, first.text)
        data = first.json()["data"]
        self.assertEqual(data["status"], "SUCCEEDED")
        self.assertTrue(data["verification"]["verified"])
        self.assertGreater(data["nodes_created"], 0)
        self.assertGreater(
            data["relationships_created"] + data["relationships_existing"],
            0)
        # Rebuild: §10 idempotency means no duplicates and no clobbering.
        # (Resolution memory may recall extra alias mentions as new nodes;
        # that is additive recall, never a rewrite of existing evidence.)
        snapshot_nodes = {k: dict(v)
                          for k, v in self.driver.store["nodes"].items()}
        snapshot_edges = {k: dict(v["props"])
                          for k, v in self.driver.store["edges"].items()}
        second = self.client.post("/api/graph/build",
                                  json={"upload_id": upload["upload_id"]})
        redo = second.json()["data"]
        self.assertTrue(redo["verification"]["verified"])
        for key, props in snapshot_nodes.items():
            self.assertIn(key, self.driver.store["nodes"])
            for prop, value in props.items():
                self.assertEqual(
                    self.driver.store["nodes"][key][prop], value)
        for key, props in snapshot_edges.items():
            self.assertIn(key, self.driver.store["edges"])
            self.assertEqual(self.driver.store["edges"][key]["props"],
                             props)

    def test_build_unknown_upload(self):
        resp = self.client.post("/api/graph/build",
                                json={"upload_id": "upl_nope"})
        self.assertEqual(resp.status_code, 404)


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class GraphUnavailableTests(unittest.TestCase):
    """No override + no NEO4J_PASSWORD in this environment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        os.environ.pop("NEO4J_PASSWORD", None)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        deps_mod.reset_graph_service()
        self.client = make_authed_client(fastapi_app)

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        deps_mod.reset_graph_service()
        self.tmp.cleanup()

    def test_graph_without_config_fails_structured(self):
        resp = self.client.get("/api/graph/person_001")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["code"], "NEO4J_CONFIG_ERROR")
        self.assertNotIn("change-me", resp.text)

    def test_build_without_neo4j_never_claims_success(self):
        resp = self.client.post("/api/graph/build",
                                json={"upload_id": "upl_anything"})
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertFalse(body["success"])


if __name__ == "__main__":
    unittest.main()
