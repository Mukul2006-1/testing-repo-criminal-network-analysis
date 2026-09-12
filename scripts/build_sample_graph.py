"""Phase 4 — deterministic sample graph for manual verification.

Builds a tiny synthetic graph (4 persons, 2 phones, 2 locations, 1 vehicle,
1 organization, 2 accounts, 2 FIRs, calls, one seeded meeting, one
transaction, usage/ownership/MENTIONED_IN edges) into a running Neo4j.

Every edge carries method + confidence + source_record_id. Edges derived
from inline synthetic evidence use their record ids; the MET and WORKS_FOR
demo links are explicitly labeled method="sample_seed" (they demonstrate
traversal, not inferred wrongdoing).

Requires a running Neo4j + NEO4J_PASSWORD (see .env.example):

    docker compose up -d neo4j
    set NEO4J_PASSWORD=...   # or export NEO4J_PASSWORD=...
    python scripts/build_sample_graph.py [--bolt-port 7687]
"""

from __future__ import annotations

import argparse
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.neo4j import Neo4jConfig, Neo4jService  # noqa: E402
from app.services.graph_builder import (  # noqa: E402
    edge_id,
    ensure_schema,
    merge_node,
    merge_relationship,
    verify_graph,
)

NODES = [
    ("Person", {"id": "person_901", "name": "Rahul Sharma",
                "normalized_name": "rahul sharma", "risk_score": 0.0}),
    ("Person", {"id": "person_902", "name": "Amit Kumar",
                "normalized_name": "amit kumar", "risk_score": 0.0}),
    ("Person", {"id": "person_903", "name": "Vikas Singh",
                "normalized_name": "vikas singh", "risk_score": 0.0}),
    ("Person", {"id": "person_904", "name": "Kavita Rao",
                "normalized_name": "kavita rao", "risk_score": 0.0}),
    ("Phone", {"id": "phone_901", "number": "+919876549001"}),
    ("Phone", {"id": "phone_902", "number": "+919876549002"}),
    ("Location", {"id": "location_901", "name": "Shanti Nagar, Delhi",
                   "latitude": 28.61, "longitude": 77.20}),
    ("Location", {"id": "location_902", "name": "Lakeview, Mumbai",
                   "latitude": 19.07, "longitude": 72.87}),
    ("Vehicle", {"id": "vehicle_901",
                  "registration_number": "DL01AB9999"}),
    ("Organization", {"id": "org_901", "name": "Sunrise Trading Co",
                       "normalized_name": "sunrise trading co"}),
    ("BankAccount", {"id": "ACC901", "account_number": "ACC901"}),
    ("BankAccount", {"id": "ACC902", "account_number": "ACC902"}),
    ("FIR", {"id": "FIR_9001", "date": "2026-02-10",
              "police_station": "Shanti Nagar Police Station",
              "source": "SYNTHETIC"}),
    ("FIR", {"id": "FIR_9002", "date": "2026-03-02",
              "police_station": "Lakeview Police Station",
              "source": "SYNTHETIC"}),
]

# (src_label, src_id, rel_type, dst_label, dst_id, source_key, props)
EDGES = [
    ("Person", "person_901", "USED", "Phone", "phone_901", "SAMPLE_01",
     {"confidence": 1.0, "source_record_id": "SAMPLE_01",
      "method": "sample_seed"}),
    ("Person", "person_902", "USED", "Phone", "phone_902", "SAMPLE_01",
     {"confidence": 1.0, "source_record_id": "SAMPLE_01",
      "method": "sample_seed"}),
    ("Phone", "phone_901", "CALLED", "Phone", "phone_902", "CDR_9001",
     {"timestamp": "2026-08-12T10:32:00Z", "duration": 420,
      "confidence": 1.0, "source_record_id": "CDR_9001",
      "method": "structured_cdr"}),
    ("Person", "person_901", "CALLED", "Person", "person_902", "CDR_9001",
     {"timestamp": "2026-08-12T10:32:00Z", "duration": 420,
      "confidence": 0.9, "source_record_id": "CDR_9001",
      "via_phones": ["+919876549001", "+919876549002"],
      "method": "structured_cdr_resolved"}),
    ("Person", "person_901", "MET", "Person", "person_903", "SAMPLE_MEET_01",
     {"timestamp": "2026-04-01T18:00:00Z", "confidence": 0.8,
      "source_record_id": "SAMPLE_MEET_01", "method": "sample_seed"}),
    ("Person", "person_901", "USED", "Vehicle", "vehicle_901", "SAMPLE_VEH_01",
     {"confidence": 1.0, "source_record_id": "SAMPLE_VEH_01",
      "method": "sample_seed"}),
    ("Person", "person_901", "OWNS", "Vehicle", "vehicle_901", "SAMPLE_VEH_01",
     {"confidence": 1.0, "source_record_id": "SAMPLE_VEH_01",
      "method": "sample_seed"}),
    ("Person", "person_901", "LOCATED_AT", "Location", "location_901",
     "SAMPLE_LOC_01",
     {"confidence": 0.8, "source_record_id": "SAMPLE_LOC_01",
      "method": "sample_seed"}),
    ("Person", "person_902", "WORKS_FOR", "Organization", "org_901",
     "SAMPLE_ORG_01",
     {"confidence": 0.9, "source_record_id": "SAMPLE_ORG_01",
      "method": "sample_seed"}),
    ("BankAccount", "ACC901", "TRANSFERRED_TO", "BankAccount", "ACC902",
     "TXN9001",
     {"transaction_id": "TXN9001", "amount": 75000, "currency": "INR",
      "timestamp": "2026-08-12T13:40:00Z", "source_id": "TXN9001",
      "confidence": 1.0, "method": "structured_transaction"}),
    ("Person", "person_901", "MENTIONED_IN", "FIR", "FIR_9001", "FIR_9001",
     {"confidence": 0.9, "source_record_id": "FIR_9001",
      "method": "sample_seed"}),
    ("Person", "person_902", "MENTIONED_IN", "FIR", "FIR_9001", "FIR_9001",
     {"confidence": 0.85, "source_record_id": "FIR_9001",
      "method": "sample_seed"}),
    ("Person", "person_903", "MENTIONED_IN", "FIR", "FIR_9002", "FIR_9002",
     {"confidence": 0.9, "source_record_id": "FIR_9002",
      "method": "sample_seed"}),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build sample demo graph.")
    parser.add_argument("--bolt-port", default=os.environ.get(
        "NEO4J_BOLT_PORT", "7687"))
    args = parser.parse_args(argv)

    env = dict(os.environ)
    env.setdefault("NEO4J_URI", f"bolt://localhost:{args.bolt_port}")
    try:
        service = Neo4jService(Neo4jConfig.from_env(env))
        service.verify()
    except Exception as exc:
        print(f"Neo4j unavailable: {exc}")
        return 1

    created_nodes = created_edges = 0
    with service.session() as session:
        ensure_schema(session)
        for label, props in NODES:
            created_nodes += merge_node(session, label, props)
        for src_label, src, rel, dst_label, dst, key, props in EDGES:
            created_edges += merge_relationship(
                session, src_label, src, rel, dst_label, dst,
                edge_id(src, rel, dst, key), props)
        verification = verify_graph(
            session, [props["id"] for _, props in NODES],
            [edge_id(src_id, rel, dst_id, key)
             for _, src_id, rel, _, dst_id, key, _ in EDGES])
    print(f"nodes: {len(NODES)} merged ({created_nodes} created)")
    print(f"edges: {len(EDGES)} merged ({created_edges} created)")
    print(f"verification: {verification}")
    service.close()
    return 0 if verification["verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
