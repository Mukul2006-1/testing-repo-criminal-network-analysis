"""Phase 5 tests — centrality, communities, anomaly detection, priority
scoring, analytics API, and full-chain integration (stdlib unittest).

Algorithm tests use small deterministic fixtures (no Neo4j). API tests use
the Phase 4 fake-driver pattern via override injection. Every test uses
isolated temporary directories: repo data/ is never touched.
"""

import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.documents import DocumentStore  # noqa: E402
from app.services import anomaly as anomaly_mod  # noqa: E402
from app.services import centrality as centrality_mod  # noqa: E402
from app.services import communities as communities_mod  # noqa: E402
from app.services import scoring as scoring_mod  # noqa: E402
from app.services.analytics import run_analytics  # noqa: E402
from app.services.validation import IngestionError  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:
    HAS_API = False

STAR_NODES = ["c", "a", "b", "d"]
STAR_EDGES = [("c", "a"), ("c", "b"), ("c", "d")]
PATH_NODES = ["n0", "n1", "n2", "n3", "n4"]
PATH_EDGES = [("n0", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4")]
CLIQUES_NODES = ["a1", "a2", "a3", "b1", "b2", "b3"]
CLIQUES_EDGES = [("a1", "a2"), ("a1", "a3"), ("a2", "a3"),
                 ("b1", "b2"), ("b1", "b3"), ("b2", "b3")]


def normal_row(entity_id, **overrides):
    row = {"entity_id": entity_id, "calls_per_day": 3.0,
           "unique_contacts": 4.0, "average_call_duration": 120.0,
           "night_calls": 0.0, "transaction_count": 2.0,
           "transaction_amount": 20000.0, "unique_locations": 2.0,
           "location_changes": 1.0}
    row.update(overrides)
    return row


def outlier_row(entity_id):
    return normal_row(entity_id, calls_per_day=67.0, unique_contacts=24.0,
                      average_call_duration=320.0, night_calls=12.0,
                      transaction_count=14.0, transaction_amount=850000.0,
                      unique_locations=9.0, location_changes=7.0)


class CentralityTests(unittest.TestCase):
    def test_empty_graph(self):
        adj = centrality_mod.build_adjacency([], [])
        self.assertEqual(adj, {})
        self.assertEqual(centrality_mod.degree_centrality(adj), {})
        self.assertEqual(centrality_mod.pagerank_raw(adj), {})
        self.assertEqual(centrality_mod.betweenness_centrality(adj), {})
        self.assertEqual(centrality_mod.analyze(adj), {})

    def test_single_node(self):
        adj = centrality_mod.build_adjacency(["solo"], [])
        result = centrality_mod.analyze(adj)["solo"]
        self.assertEqual(result["degree"], 0)
        self.assertEqual(result["pagerank"], 0.0)
        self.assertEqual(result["betweenness"], 0.0)

    def test_disconnected_nodes(self):
        adj = centrality_mod.build_adjacency(["a", "b"], [])
        for value in centrality_mod.analyze(adj).values():
            self.assertEqual((value["degree"], value["pagerank"],
                              value["betweenness"]), (0, 0.0, 0.0))

    def test_star_center_dominates(self):
        adj = centrality_mod.build_adjacency(STAR_NODES, STAR_EDGES)
        degrees = centrality_mod.degree_centrality(adj)
        self.assertEqual(degrees, {"c": 3, "a": 1, "b": 1, "d": 1})
        order = [nid for nid, _ in
                 centrality_mod.ranked(centrality_mod.pagerank_raw(adj))]
        self.assertEqual(order[0], "c")
        betweenness = centrality_mod.betweenness_centrality(adj)
        self.assertEqual(betweenness["c"], 1.0)
        self.assertTrue(all(betweenness[n] == 0.0 for n in "abd"))

    def test_pagerank_sums_to_one_and_deterministic(self):
        adj = centrality_mod.build_adjacency(PATH_NODES, PATH_EDGES)
        first = centrality_mod.pagerank_raw(adj)
        second = centrality_mod.pagerank_raw(adj)
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(first.values()), 1.0, places=6)

    def test_path_betweenness_middle_highest(self):
        adj = centrality_mod.build_adjacency(PATH_NODES, PATH_EDGES)
        betweenness = centrality_mod.betweenness_centrality(adj)
        self.assertGreater(betweenness["n2"], betweenness["n1"])
        self.assertGreater(betweenness["n1"], betweenness["n0"])
        for value in betweenness.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_minmax_degenerate(self):
        self.assertEqual(centrality_mod.minmax_norm({}), {})
        self.assertEqual(centrality_mod.minmax_norm({"a": 0.5, "b": 0.5}),
                         {"a": 0.0, "b": 0.0})

    def test_sanitize_never_leaks_nan(self):
        for bad in (float("nan"), float("inf"), float("-inf"), "x", None):
            self.assertEqual(centrality_mod.sanitize_score(bad), 0.0)
        self.assertEqual(centrality_mod.sanitize_score(2.0), 1.0)
        self.assertEqual(centrality_mod.sanitize_score(-1.0), 0.0)


class CommunityTests(unittest.TestCase):
    def test_empty_and_single(self):
        self.assertEqual(communities_mod.louvain({}), {})
        self.assertEqual(communities_mod.louvain({"a": set()}), {"a": 0})

    def test_two_cliques_split(self):
        partition = communities_mod.louvain(
            centrality_mod.build_adjacency(CLIQUES_NODES, CLIQUES_EDGES))
        self.assertEqual(partition["a1"], partition["a2"])
        self.assertEqual(partition["a2"], partition["a3"])
        self.assertEqual(partition["b1"], partition["b2"])
        self.assertNotEqual(partition["a1"], partition["b1"])
        self.assertEqual(sorted(set(partition.values())), [0, 1])

    def test_deterministic(self):
        adj = centrality_mod.build_adjacency(CLIQUES_NODES,
                                             CLIQUES_EDGES + [("a3", "b1")])
        self.assertEqual(communities_mod.louvain(adj),
                         communities_mod.louvain(adj))

    def test_isolates_own_communities(self):
        partition = communities_mod.louvain(
            centrality_mod.build_adjacency(["a", "b"], []))
        self.assertNotEqual(partition["a"], partition["b"])


class AnomalyTests(unittest.TestCase):
    def test_obvious_outlier_flagged(self):
        rows = [normal_row(f"p{i:02d}") for i in range(11)]
        rows.append(outlier_row("outlier"))
        results = anomaly_mod.detect(rows)
        by_id = {row["entity_id"]: row for row in results}
        self.assertEqual(by_id["outlier"]["severity"], "HIGH")
        self.assertGreater(by_id["outlier"]["anomaly_score"], 0.8)
        self.assertIn("Communication spike",
                      by_id["outlier"]["reasons"])
        normals_high = [row for row in results
                        if row["entity_id"] != "outlier"
                        and row["severity"] == "HIGH"]
        self.assertEqual(normals_high, [])

    def test_empty_dataset(self):
        self.assertEqual(anomaly_mod.detect([]), [])

    def test_single_entity_default(self):
        results = anomaly_mod.detect([normal_row("solo")])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["anomaly_score"], 0.0)
        self.assertEqual(results[0]["severity"], "LOW")
        self.assertTrue(results[0]["reasons"])

    def test_constant_features_default(self):
        results = anomaly_mod.detect([normal_row("a"), normal_row("b")])
        self.assertTrue(all(row["severity"] == "LOW" for row in results))
        self.assertTrue(all(row["anomaly_score"] == 0.0 for row in results))

    def test_missing_and_zero_values_safe(self):
        rows = [normal_row("a", night_calls=None, transaction_amount=None),
                normal_row("b", calls_per_day=0.0,
                           average_call_duration=0.0, transaction_count=0.0,
                           transaction_amount=0.0, unique_locations=0.0,
                           location_changes=0.0)]
        for row in anomaly_mod.detect(rows + [outlier_row("c")]):
            self.assertTrue(math.isfinite(row["anomaly_score"]))
            for value in row["features"].values():
                self.assertTrue(math.isfinite(value))

    def test_reproducible(self):
        rows = [normal_row(f"p{i:02d}") for i in range(8)]
        rows.append(outlier_row("outlier"))
        first = anomaly_mod.detect(rows)
        second = anomaly_mod.detect(rows)
        self.assertEqual(first, second)

    def test_severity_mapping(self):
        self.assertEqual(anomaly_mod.severity_for(0.8), "HIGH")
        self.assertEqual(anomaly_mod.severity_for(0.79), "MEDIUM")
        self.assertEqual(anomaly_mod.severity_for(0.5), "MEDIUM")
        self.assertEqual(anomaly_mod.severity_for(0.49), "LOW")
        self.assertEqual(anomaly_mod.severity_for(0.0), "LOW")

    def test_reasons_grounded_in_evidence(self):
        rows = [normal_row(f"p{i:02d}") for i in range(10)]
        rows.append(outlier_row("outlier"))
        by_id = {row["entity_id"]: row
                 for row in anomaly_mod.detect(rows)}
        reasons = by_id["outlier"]["reasons"]
        self.assertIn("Large transaction activity", reasons)
        self.assertIn("Unusual night-call activity", reasons)
        quiet = normal_row("quiet", calls_per_day=1.0, unique_contacts=1.0,
                           night_calls=0.0, transaction_count=0.0,
                           transaction_amount=0.0, unique_locations=1.0,
                           location_changes=0.0)
        calm = anomaly_mod.detect([quiet] + rows[:5])
        self.assertEqual(
            [row for row in calm if row["entity_id"] == "quiet"][0]["reasons"],
            [])

    def test_invalid_contamination(self):
        with self.assertRaises(IngestionError):
            anomaly_mod.detect([normal_row("a")], contamination=0.0)
        with self.assertRaises(IngestionError):
            anomaly_mod.detect([normal_row("a")], contamination=0.9)

    def test_feature_aggregation(self):
        calls = [{"timestamp": "2026-08-01T10:00:00Z", "duration": 100,
                  "contact": "x"},
                 {"timestamp": "2026-08-01T02:00:00Z", "duration": 300,
                  "contact": "y"},
                 {"timestamp": "2026-08-02T10:00:00Z", "duration": 200,
                  "contact": "x"}]
        features = anomaly_mod.features_for_person(
            calls, [{"timestamp": "2026-08-01T12:00:00Z", "amount": 50000}],
            [{"date": "2026-08-01", "location": "A"},
             {"date": "2026-08-02", "location": "B"}], window_days=2)
        self.assertEqual(features,
                         {"calls_per_day": 1.5, "unique_contacts": 2.0,
                          "average_call_duration": 200.0, "night_calls": 1.0,
                          "transaction_count": 1.0,
                          "transaction_amount": 50000.0,
                          "unique_locations": 2.0, "location_changes": 1.0})


class ScoringTests(unittest.TestCase):
    def test_exact_formula(self):
        result = scoring_mod.priority_score(0.82, 0.77, 0.91)
        self.assertAlmostEqual(result["score"], 0.8295, places=4)
        self.assertEqual(result["priority"], 83)
        self.assertEqual(result["components"],
                         {"pagerank": 0.82, "betweenness": 0.77,
                          "anomaly_score": 0.91})

    def test_bounds(self):
        result = scoring_mod.priority_score(0.0, 0.0, 0.0)
        self.assertEqual((result["score"], result["priority"]), (0.0, 0))
        result = scoring_mod.priority_score(1.0, 1.0, 1.0)
        self.assertEqual((result["score"], result["priority"]), (1.0, 100))
        for pr, bw, an in ((0.2, 0.9, 0.1), (1.0, 0.0, 0.5), (0.33, 0.33, 0.34)):
            result = scoring_mod.priority_score(pr, bw, an)
            self.assertGreaterEqual(result["score"], 0.0)
            self.assertLessEqual(result["score"], 1.0)
            self.assertGreaterEqual(result["priority"], 0)
            self.assertLessEqual(result["priority"], 100)

    def test_priority_integer_conversion(self):
        self.assertEqual(scoring_mod.priority_score(0.5, 0.5, 0.5)["priority"],
                         50)
        self.assertEqual(
            scoring_mod.priority_score(0.0, 0.0, 0.01)["priority"], 0)

    def test_invalid_inputs(self):
        # NaN is sanitized to 0.0 (no NaN may leak); non-numeric raises.
        result = scoring_mod.priority_score(float("nan"), 0.5, 0.5)
        self.assertAlmostEqual(result["score"], 0.35 * 0.0 + 0.35 * 0.5 +
                               0.30 * 0.5, places=4)
        with self.assertRaises(IngestionError):
            scoring_mod.priority_score("high", 0.5, 0.5)

    def test_reasons(self):
        reasons = scoring_mod.explain_score(0.9, 0.1, 0.1)
        self.assertIn("High structural importance in the network", reasons)
        reasons = scoring_mod.explain_score(0.1, 0.85, 0.1)
        self.assertIn("Acts as a bridge between network groups", reasons)
        reasons = scoring_mod.explain_score(0.1, 0.1, 0.95)
        self.assertIn("Unusual activity pattern", reasons)
        reasons = scoring_mod.explain_score(0.1, 0.1, 0.1, high_degree=True,
                                            community_size=5)
        self.assertIn("Highly connected entity", reasons)
        self.assertIn("Connected to a dense network group", reasons)
        self.assertEqual(scoring_mod.explain_score(0.1, 0.1, 0.1), [])

    def test_no_forbidden_language(self):
        for text in (scoring_mod.FORMULA, scoring_mod.DISCLAIMER,
                     " ".join(scoring_mod.explain_score(1.0, 1.0, 1.0,
                                                       True, 5))):
            for forbidden in ("criminal probability", "guilt probability",
                              "crime probability", "threat probability"):
                self.assertNotIn(forbidden, text.lower())


def load_sample_graph():
    """Phase 4 deterministic fixture (scripts/build_sample_graph.py)."""
    path = os.path.join(REPO_ROOT, "scripts", "build_sample_graph.py")
    spec = importlib.util.spec_from_file_location("build_sample_graph", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NODES, module.EDGES


class ChainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.database.documents import DocumentStore

        self.store = DocumentStore(os.path.join(self.tmp.name, "docs.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_person(self, pid, name, normed):
        from app.services.entity_resolution import resolve_one

        return resolve_one(self.store, "PERSON", name, normed, 0.9,
                           "seed", "SEED_DOC")

    def test_full_chain_on_fixture(self):
        nodes = ["p1", "p2", "p3", "p4"]
        edges = [("p1", "p2"), ("p2", "p3"), ("p3", "p4"), ("p1", "p3")]
        canonical = {}
        for pid in nodes:
            result = self._seed_person(pid, f"Name {pid}", pid)
            canonical[pid] = result["canonical_id"]
        canon_edges = [(canonical[src], canonical[dst]) for src, dst in edges]
        canon_nodes = [{"id": cid} for cid in canonical.values()]
        summary = run_analytics(self.store, canon_nodes, canon_edges, [])
        self.assertEqual(summary["entities_scored"], 4)
        self.assertEqual(summary["window_days"], 1)
        self.assertEqual(len(summary["top"]), 4)
        for pid in canonical.values():
            stored = self.store.get_analytics(pid)
            for key in ("degree", "pagerank", "betweenness", "community_id"):
                self.assertIn(key, stored)
            anomaly = self.store.latest_anomaly(pid)
            self.assertIn(anomaly["severity"], ("LOW", "MEDIUM", "HIGH"))
            self.assertGreaterEqual(anomaly["score"], 0.0)
            self.assertLessEqual(anomaly["score"], 1.0)

    def test_phase4_sample_graph_scores(self):
        nodes, edges = load_sample_graph()
        adjacency = centrality_mod.build_adjacency(
            [props["id"] for _, props in nodes],
            [(src, dst) for _, src, _, _, dst, _, _ in edges])
        metrics = centrality_mod.analyze(adjacency)
        self.assertIn("person_901", metrics)
        self.assertGreater(metrics["person_901"]["degree"], 0)
        partition = communities_mod.louvain(adjacency)
        self.assertEqual(set(partition), set(adjacency))
        for value in list(metrics["person_901"].values()):
            self.assertTrue(math.isfinite(float(value)))


def _load_sibling(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class AnalyticsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        from app.database.neo4j import Neo4jConfig, Neo4jService

        FakeDriver = _load_sibling("test_graph").FakeDriver
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

    def _prepare(self):
        for filename, dtype in (("cdr.csv", "CDR"), ("fir.csv", "FIR"),
                                ("transactions.csv", "TRANSACTION")):
            with open(os.path.join(REPO_ROOT, "data", "sample", filename),
                      "rb") as fh:
                content = fh.read()
            upload = self.client.post(
                "/api/upload",
                files={"file": (filename, content, "text/csv")},
                data={"dataset_type": dtype}).json()["data"]
            proc = self.client.post("/api/process",
                                    json={"upload_id": upload["upload_id"]})
            self.assertEqual(proc.status_code, 200)
            # Real pipeline order: resolution + graph build precede scoring.
            build = self.client.post("/api/graph/build",
                                     json={"upload_id": upload["upload_id"]})
            self.assertEqual(build.status_code, 200, build.text)

    def _run(self):
        self._prepare()
        resp = self.client.post("/api/analytics/run", json={})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]

    def test_run_and_endpoints(self):
        summary = self._run()
        self.assertGreater(summary["entities_scored"], 0)
        self.assertEqual(len(summary["top"]), 5)
        self.assertIn("disclaimer", summary)
        for path in ("/api/analytics/pagerank", "/api/analytics/betweenness",
                     "/api/analytics/communities", "/api/analytics/degree"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            data = resp.json()["data"]
            self.assertIn("items", data)
            self.assertIn("pagination", data)
            self.assertIn("disclaimer", data)
        first_id = summary["top"][0]["entity_id"]
        single = self.client.get(
            f"/api/analytics/pagerank?entity_id={first_id}")
        self.assertEqual(single.status_code, 200)
        self.assertEqual(
            self.client.get("/api/analytics/pagerank?entity_id=ghost")
            .status_code, 404)
        anomalies = self.client.get("/api/anomalies")
        self.assertEqual(anomalies.status_code, 200, anomalies.text)
        items = anomalies.json()["data"]["items"]
        self.assertGreater(len(items), 0)
        item = items[0]
        for key in ("entity_id", "features", "anomaly_score", "severity",
                    "reasons"):
            self.assertIn(key, item)
        self.assertEqual(len(item["features"]), 8)
        high = self.client.get("/api/anomalies?severity=HIGH")
        self.assertEqual(high.status_code, 200)
        self.assertTrue(all(row["severity"] == "HIGH"
                            for row in high.json()["data"]["items"]))
        self.assertEqual(
            self.client.get("/api/anomalies?severity=EVIL").status_code, 422)

    def test_investigation(self):
        summary = self._run()
        entity_id = summary["top"][0]["entity_id"]
        resp = self.client.get(f"/api/investigation/{entity_id}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        for key in ("entity", "priority", "graph_metrics", "anomaly",
                    "explanations", "timeline_ref", "key_relationships",
                    "sources"):
            self.assertIn(key, data)
        self.assertEqual(data["priority"]["formula_version"], "v1")
        self.assertIn("disclaimer", data["priority"])
        blob = json.dumps(data).lower()
        for forbidden in ("criminal probability", "guilt probability",
                          "crime probability", "threat probability",
                          "guilt score"):
            self.assertNotIn(forbidden, blob)
        detail = self.client.get(f"/api/entities/{entity_id}")
        summary_block = detail.json()["data"]["analytics_summary"]
        for key in ("degree", "pagerank", "betweenness", "community_id",
                    "anomaly_score", "priority_score"):
            self.assertIn(key, summary_block)
        self.assertEqual(
            self.client.get("/api/investigation/ghost").status_code, 404)

    def test_no_nan_in_payloads(self):
        summary = self._run()
        bodies = []
        for path in ("/api/analytics/pagerank", "/api/anomalies",
                     f"/api/investigation/{summary['top'][0]['entity_id']}"):
            bodies.append(self.client.get(path).text)
        for body in bodies:
            self.assertNotIn("NaN", body)
            self.assertNotIn("Infinity", body)
            json.loads(body)

    def test_run_requires_neo4j(self):
        from app.api import deps as deps_mod

        deps_mod.reset_graph_service()
        os.environ.pop("NEO4J_PASSWORD", None)
        resp = self.client.post("/api/analytics/run", json={})
        self.assertEqual(resp.status_code, 500)
        self.assertIn(resp.json()["error"]["code"],
                      ("NEO4J_CONFIG_ERROR", "NEO4J_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main()
