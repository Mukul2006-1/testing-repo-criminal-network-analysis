"""Phase 4 — Neo4j graph builder (NEO4J_SCHEMA.md contract).

Centralized mappings (no scattered literals), parameterized Cypher only,
idempotent MERGE writes keyed by stable canonical IDs and deterministic
edge IDs. Relationships are created exclusively from structured source
data or explicit caller-supplied evidence — never from co-occurrence.
"""

from __future__ import annotations

import hashlib

from ..database.neo4j import QUERY_TIMEOUT_SECONDS
from . import nlp as nlp_mod
from .entity_resolution import resolve_document
from .validation import IngestionError

# -- centralized mappings (NEO4J_SCHEMA.md §§2, 11-13) -----------------------
ENTITY_LABEL = {
    "PERSON": "Person",
    "PHONE": "Phone",
    "LOCATION": "Location",
    "VEHICLE": "Vehicle",
    "ORGANIZATION": "Organization",
    "ACCOUNT": "BankAccount",
    "FIR": "FIR",
    # DATE has no node: it is a property per the schema mapping.
}
LABEL_ENTITY = {label: etype for etype, label in ENTITY_LABEL.items()}

REL_TYPES = (
    "CALLED", "MET", "LOCATED_AT", "OWNS", "USED", "TRANSFERRED_TO",
    "ASSOCIATED_WITH", "MENTIONED_IN", "WORKS_FOR", "TRAVELLED_TO",
)
# Legacy alias from older loaders: normalized to USED, never stored as USES.
REL_ALIASES = {"USES": "USED"}

CONSTRAINTS = [
    ("person_id_unique", "Person"), ("phone_id_unique", "Phone"),
    ("location_id_unique", "Location"), ("vehicle_id_unique", "Vehicle"),
    ("organization_id_unique", "Organization"),
    ("bankaccount_id_unique", "BankAccount"), ("fir_id_unique", "FIR"),
    ("crime_id_unique", "Crime"),
]
INDEXES = [
    ("person_normalized_name", "Person", "normalized_name"),
    ("person_name", "Person", "name"),
    ("phone_number", "Phone", "number"),
    ("vehicle_reg", "Vehicle", "registration_number"),
    ("org_normalized_name", "Organization", "normalized_name"),
    ("location_name", "Location", "name"),
]


def normalize_rel_type(rel_type: str) -> str:
    """Map an application relationship to its Neo4j type or reject it.

    Unknown types are rejected (never passed into Cypher); the legacy
    USES alias converges to USED per NEO4J_SCHEMA.md §13.
    """
    canonical = REL_ALIASES.get(str(rel_type), str(rel_type))
    if canonical not in REL_TYPES:
        raise IngestionError("UNSUPPORTED_RELATIONSHIP",
                             f"Relationship type '{rel_type}' is not in the "
                             f"project schema.",
                             http_status=422)
    return canonical


def node_props(entity_type: str, canonical: dict) -> dict:
    """Property map for one canonical entity. DATE has no node (None)."""
    cid = canonical["id"]
    if entity_type == "PERSON":
        return {"id": cid, "name": canonical["canonical_name"],
                "normalized_name": canonical["normalized_name"],
                "risk_score": 0.0}
    if entity_type == "PHONE":
        return {"id": cid, "number": canonical["normalized_name"]}
    if entity_type == "LOCATION":
        return {"id": cid, "name": canonical["canonical_name"],
                "latitude": None, "longitude": None}
    if entity_type == "VEHICLE":
        return {"id": cid,
                "registration_number": canonical["normalized_name"]}
    if entity_type == "ORGANIZATION":
        return {"id": cid, "name": canonical["canonical_name"],
                "normalized_name": canonical["normalized_name"]}
    if entity_type == "ACCOUNT":
        return {"id": cid, "account_number": canonical["normalized_name"]}
    return None  # DATE and anything future without a node mapping


def edge_id(source_id: str, rel_type: str, target_id: str,
            source_key: str = "") -> str:
    """Deterministic edge identity: same evidence re-run => same edge."""
    raw = f"{source_id}|{rel_type}|{target_id}|{source_key or ''}"
    return f"rel_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _counters(result) -> tuple[int, int]:
    # neo4j driver v5: Result.consume() -> ResultSummary.counters.
    counters = result.consume().counters
    return (getattr(counters, "nodes_created", 0),
            getattr(counters, "relationships_created", 0))


def ensure_schema(session) -> None:
    """Create uniqueness constraints + indexes (idempotent DDL).

    Labels/names come only from the internal mapping above — never from
    user input — so interpolation here is safe; all values stay parameterized.
    """
    for name, label in CONSTRAINTS:
        session.run(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE",
            timeout=QUERY_TIMEOUT_SECONDS)
    for name, label, prop in INDEXES:
        session.run(
            f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})",
            timeout=QUERY_TIMEOUT_SECONDS)


def merge_node(session, label: str, props: dict) -> bool:
    """MERGE one node by (label, id). Returns True when created.

    First-write-wins: re-merges never overwrite existing properties, so
    repeated ingestion is a pure no-op and original evidence (including
    provenance) is never silently modified. Corrections, when needed,
    are explicit operations — not side effects of a rebuild.
    """
    if label not in LABEL_ENTITY:
        raise IngestionError("UNSUPPORTED_NODE_LABEL",
                             f"Node label '{label}' is not in the schema.",
                             http_status=422)
    result = session.run(
        f"MERGE (n:{label} {{id: $id}}) ON CREATE SET n = $props",
        {"id": props["id"], "props": props},
        timeout=QUERY_TIMEOUT_SECONDS)
    created, _ = _counters(result)
    return created > 0


def merge_relationship(session, src_label: str, src_id: str, rel_type: str,
                       dst_label: str, dst_id: str, edge_id_: str,
                       props: dict) -> bool:
    """MERGE one directed edge by deterministic edge id. Returns True new.

    First-write-wins (see merge_node): re-merges never touch existing
    edge properties.
    """
    rel = normalize_rel_type(rel_type)
    if src_label not in LABEL_ENTITY or dst_label not in LABEL_ENTITY:
        raise IngestionError("UNSUPPORTED_NODE_LABEL",
                             "Relationship endpoint label not in schema.",
                             http_status=422)
    result = session.run(
        f"MATCH (a:{src_label} {{id: $src_id}}), "
        f"(b:{dst_label} {{id: $dst_id}}) "
        f"MERGE (a)-[r:{rel} {{id: $edge_id}}]->(b) "
        "ON CREATE SET r = $props",
        {"src_id": src_id, "dst_id": dst_id, "edge_id": edge_id_,
         "props": {"id": edge_id_, **props}},
        timeout=QUERY_TIMEOUT_SECONDS)
    _, created = _counters(result)
    return created > 0


def build_gazetteer(store) -> tuple[list[str], list[str]]:
    """Alias memory from resolved entities (read-only). Shared with the
    extract endpoint so both improve as resolution memory grows."""
    names, locations = set(), set()
    for entity_type, bucket in (("PERSON", names), ("ORGANIZATION", names),
                                ("LOCATION", locations)):
        for entity in store.list_entities_by_type(entity_type):
            bucket.add(entity["canonical_name"])
            for mention in store.list_mentions(entity["id"], limit=100):
                bucket.add(mention["text"])
    return sorted(names), sorted(locations)


def person_by_phone(store) -> dict[str, str]:
    """Map normalized phone number -> person canonical id (resolution attrs)."""
    mapping = {}
    for person in store.list_entities_by_type("PERSON"):
        for number in (person.get("attributes") or {}).get("phones", []):
            mapping.setdefault(str(number), person["id"])
    return mapping


def write_graph(session, nodes: list[dict],
                relationships: list[dict]) -> dict:
    """Write nodes + relationships with full counts. Pure execution: all
    inputs must already be validated/mapped by the caller."""
    counts = {"nodes_created": 0, "nodes_existing": 0,
              "relationships_created": 0, "relationships_existing": 0,
              "skipped": [], "errors": []}
    built_ids = set()
    for node in nodes:
        try:
            if merge_node(session, node["label"], node["props"]):
                counts["nodes_created"] += 1
            else:
                counts["nodes_existing"] += 1
            built_ids.add(node["props"]["id"])
        except IngestionError as exc:
            counts["errors"].append({"code": exc.code,
                                     "message": exc.message})
    for rel in relationships:
        try:
            if rel["source_id"] not in built_ids or \
                    rel["target_id"] not in built_ids:
                counts["skipped"].append(
                    {"edge": rel.get("edge_id"),
                     "reason": "endpoint node not built"})
                continue
            if merge_relationship(
                    session, rel["source_label"], rel["source_id"],
                    rel["type"], rel["target_label"], rel["target_id"],
                    rel["edge_id"], rel.get("props", {})):
                counts["relationships_created"] += 1
            else:
                counts["relationships_existing"] += 1
        except IngestionError as exc:
            counts["errors"].append({"code": exc.code,
                                     "message": exc.message})
    return counts


def verify_graph(session, node_ids: list[str],
                 edge_ids: list[str]) -> dict:
    """Confirm built IDs exist. Returns missing lists (empty = verified)."""
    missing_nodes, missing_edges = [], []
    if node_ids:
        result = session.run(
            "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id",
            {"ids": list(node_ids)}, timeout=QUERY_TIMEOUT_SECONDS)
        # Record["id"] works for both driver Records and plain dicts.
        found = {record["id"] for record in result}
        missing_nodes = [nid for nid in node_ids if nid not in found]
    for eid in edge_ids:
        result = session.run(
            "MATCH ()-[r {id: $eid}]->() RETURN r.id AS id",
            {"eid": eid}, timeout=QUERY_TIMEOUT_SECONDS)
        rows = list(result)
        if not rows:
            missing_edges.append(eid)
    return {"missing_nodes": missing_nodes, "missing_edges": missing_edges,
            "verified": not missing_nodes and not missing_edges}


def _node_for(store, canonical_id: str) -> dict | None:
    entity = store.get_entity(canonical_id)
    if entity is None:
        return None
    label = ENTITY_LABEL.get(entity["type"])
    if label is None:
        return None  # DATE and unmapped types have no node
    props = node_props(entity["type"], entity)
    return {"label": label, "props": props}


def build_from_upload(store, upload_id: str, records: list[dict]) -> tuple[
        list[dict], list[dict], dict]:
    """Compose nodes + evidence-backed relationships for one upload.

    Sources of truth per record: structured identifiers (CDR callers,
    transaction accounts, vehicle owner fields) and FIR text mentions.
    Co-occurrence alone never creates an edge. Returns
    (nodes, relationships, notes) where notes records skips.
    """
    names, locations = build_gazetteer(store)
    phone_owner = person_by_phone(store)
    nodes: dict[str, dict] = {}
    relationships: list[dict] = []
    notes = {"skipped": []}

    def add_node(canonical_id: str) -> dict | None:
        if canonical_id in nodes:
            return nodes[canonical_id]
        node = _node_for(store, canonical_id)
        if node is None:
            notes["skipped"].append({"canonical_id": canonical_id,
                                     "reason": "no node mapping"})
            return None
        nodes[canonical_id] = node
        return node

    def add_edge(src_id: str, rel_type: str, dst_id: str,
                 source_key: str, props: dict) -> None:
        src = nodes.get(src_id)
        dst = nodes.get(dst_id)
        if src is None or dst is None:
            notes["skipped"].append(
                {"edge": f"{src_id}-{rel_type}-{dst_id}",
                 "reason": "endpoint node not built"})
            return
        relationships.append({
            "source_label": src["label"], "source_id": src_id,
            "type": normalize_rel_type(rel_type),
            "target_label": dst["label"], "target_id": dst_id,
            "edge_id": edge_id(src_id, normalize_rel_type(rel_type),
                               dst_id, source_key),
            "props": props,
        })

    for index, record in enumerate(records):
        source_type = record.get("source_type")
        source_id = record.get("source_id", f"{upload_id}#R{index}")
        normalized = record.get("normalized") or {}

        if source_type == "FIR":
            fir_node_id = str(normalized.get("fir_id") or source_id)
            nodes[fir_node_id] = {
                "label": "FIR",
                "props": {"id": fir_node_id,
                          "date": normalized.get("date"),
                          "police_station": normalized.get("police_station"),
                          "source": normalized.get("source")},
            }
            text = normalized.get("text", "")
            extraction = nlp_mod.extract_entities(
                text, source_id, known_names=names,
                known_locations=locations)
            resolved = resolve_document(store, source_id,
                                        extraction["entities"])
            for item in resolved["resolved"]:
                node = add_node(item["canonical_id"])
                if node is None:
                    continue
                confs = [m["confidence"] for m in item["matches"]] or [0.0]
                add_edge(item["canonical_id"], "MENTIONED_IN", fir_node_id,
                         source_id,
                         {"confidence": max(confs),
                          "source_record_id": source_id,
                          "method": "+".join(item["resolution_method"])})

        elif source_type == "CDR":
            caller = normalized.get("caller")
            receiver = normalized.get("receiver")
            if not caller or not receiver:
                notes["skipped"].append({"record": source_id,
                                         "reason": "missing caller/receiver"})
                continue
            call = {"timestamp": normalized.get("timestamp"),
                    "duration": normalized.get("duration"),
                    "source_record_id": source_id, "confidence": 1.0,
                    "method": "structured_cdr"}
            for number in (caller, receiver):
                resolved = resolve_document(store, source_id, [
                    nlp_mod.structured_entity("PHONE", str(number),
                                              source_field="cdr")])
                add_node(resolved["resolved"][0]["canonical_id"])
            caller_nodes = [n for n in nodes.values()
                            if n["label"] == "Phone"
                            and n["props"].get("number") == caller]
            receiver_nodes = [n for n in nodes.values()
                              if n["label"] == "Phone"
                              and n["props"].get("number") == receiver]
            if caller_nodes and receiver_nodes:
                add_edge(caller_nodes[0]["props"]["id"], "CALLED",
                         receiver_nodes[0]["props"]["id"], source_id, call)
            person_a, person_b = (phone_owner.get(caller),
                                  phone_owner.get(receiver))
            if person_a and person_b and person_a != person_b:
                for pid in (person_a, person_b):
                    add_node(pid)
                add_edge(person_a, "CALLED", person_b, source_id,
                         {**call, "confidence": 0.9,
                          "via_phones": [caller, receiver],
                          "method": "structured_cdr_resolved"})

        elif source_type == "TRANSACTION":
            sender = normalized.get("sender_account")
            receiver = normalized.get("receiver_account")
            if not sender or not receiver:
                notes["skipped"].append({"record": source_id,
                                         "reason": "missing account"})
                continue
            for acct in (sender, receiver):
                resolved = resolve_document(store, source_id, [
                    nlp_mod.structured_entity("ACCOUNT", str(acct),
                                              source_field="transaction")])
                add_node(resolved["resolved"][0]["canonical_id"])
            senders = [n for n in nodes.values()
                       if n["label"] == "BankAccount"
                       and n["props"].get("account_number") == sender]
            receivers = [n for n in nodes.values()
                         if n["label"] == "BankAccount"
                         and n["props"].get("account_number") == receiver]
            if senders and receivers:
                add_edge(senders[0]["props"]["id"], "TRANSFERRED_TO",
                         receivers[0]["props"]["id"], source_id,
                         {"transaction_id": normalized.get("transaction_id"),
                          "amount": normalized.get("amount"),
                          "currency": normalized.get("currency"),
                          "timestamp": normalized.get("timestamp"),
                          "source_id": source_id, "confidence": 1.0,
                          "method": "structured_transaction"})

        elif source_type == "VEHICLE":
            reg = normalized.get("registration_number")
            owner = normalized.get("owner_name") or \
                (record.get("original") or {}).get("owner_name")
            if not reg or not owner:
                notes["skipped"].append({"record": source_id,
                                         "reason": "missing vehicle/owner"})
                continue
            resolved = resolve_document(store, source_id, [
                nlp_mod.structured_entity("VEHICLE", str(reg),
                                          source_field="vehicle_record")])
            vehicle_node = add_node(resolved["resolved"][0]["canonical_id"])
            owner_ext = nlp_mod.extract_entities(
                str(owner), source_id, known_names=names)
            owner_res = resolve_document(
                store, source_id,
                owner_ext["entities"] or [nlp_mod.structured_entity(
                    "PERSON", str(owner), source_field="owner_name")])
            person_node = add_node(owner_res["resolved"][0]["canonical_id"])
            if vehicle_node and person_node:
                edge_props = {"source_record_id": source_id,
                              "confidence": 1.0,
                              "method": "structured_vehicle_record"}
                add_edge(person_node["props"]["id"], "USED",
                         vehicle_node["props"]["id"], source_id, edge_props)
                add_edge(person_node["props"]["id"], "OWNS",
                         vehicle_node["props"]["id"], source_id, edge_props)

        elif source_type == "LOCATION":
            name = normalized.get("name")
            if not name:
                notes["skipped"].append({"record": source_id,
                                         "reason": "missing location name"})
                continue
            resolved = resolve_document(store, source_id, [
                nlp_mod.structured_entity("LOCATION", str(name),
                                          source_field="location_record")])
            node = add_node(resolved["resolved"][0]["canonical_id"])
            if node is not None:
                node["props"]["latitude"] = normalized.get("latitude")
                node["props"]["longitude"] = normalized.get("longitude")
        else:
            notes["skipped"].append({"record": source_id,
                                     "reason": f"unknown source_type "
                                               f"{source_type}"})

    return list(nodes.values()), relationships, notes
