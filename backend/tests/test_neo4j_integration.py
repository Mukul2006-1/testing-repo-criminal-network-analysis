"""Phase 4 — live Neo4j integration tests (opt-in, clearly marked).

These tests require a running Neo4j 5 instance and are SKIPPED unless
NEO4J_TESTS=1 is set. They never touch developer data: every node/edge id
uses the "itest_" prefix and is removed afterwards.

Setup (local, using this repo's compose service):

    docker compose up -d neo4j
    copy .env.example .env   # then set a local-only NEO4J_PASSWORD
    set NEO4J_PASSWORD=<your-local-password>   # PowerShell
    set NEO4J_TESTS=1
    python backend/tests/test_neo4j_integration.py
"""

import os
import sys
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

RUN_LIVE = os.environ.get("NEO4J_TESTS") == "1"


@unittest.skipUnless(RUN_LIVE, "NEO4J_TESTS != 1 (needs a running Neo4j)")
class LiveNeo4jTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = Neo4jService(Neo4jConfig.from_env())
        cls.service.verify()

    @classmethod
    def tearDownClass(cls):
        with cls.service.session() as session:
            session.run(
                "MATCH (n) WHERE n.id STARTS WITH 'itest_' "
                "DETACH DELETE n")
        cls.service.close()

    def test_constraints_and_crud_idempotent(self):
        with self.service.session() as session:
            ensure_schema(session)
            created = merge_node(
                session, "Person",
                {"id": "itest_person_1", "name": "Itest Person",
                 "normalized_name": "itest person", "risk_score": 0.0})
            self.assertTrue(created)
            self.assertFalse(merge_node(
                session, "Person",
                {"id": "itest_person_1", "name": "Itest Person",
                 "normalized_name": "itest person", "risk_score": 0.0}))
            merge_node(session, "Person",
                       {"id": "itest_person_2", "name": "Itest Two",
                        "normalized_name": "itest two", "risk_score": 0.0})
            eid = edge_id("itest_person_1", "MET", "itest_person_2",
                          "ITEST_1")
            self.assertTrue(merge_relationship(
                session, "Person", "itest_person_1", "MET", "Person",
                "itest_person_2", eid,
                {"confidence": 0.8, "source_record_id": "ITEST_1",
                 "method": "integration_test"}))
            self.assertFalse(merge_relationship(
                session, "Person", "itest_person_1", "MET", "Person",
                "itest_person_2", eid,
                {"confidence": 0.8, "source_record_id": "ITEST_1",
                 "method": "integration_test"}))
            verification = verify_graph(
                session, ["itest_person_1", "itest_person_2"], [eid])
            self.assertTrue(verification["verified"])


if __name__ == "__main__":
    unittest.main()
