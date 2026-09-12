"""Phase 6 end-to-end test — full pipeline with authentication.

Upload sample FIR → process → NLP extract → resolve → Neo4j (fake) build
→ analytics run → anomalies → investigation → timeline → search →
entity detail. Asserts real data flows across every stage boundary with
no hardcoded values. Isolated temp dirs; repo data never touched.
"""

import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:
    HAS_API = False


def _load_sibling(name):
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class EndToEndTests(unittest.TestCase):
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
        self.client = make_authed_client(fastapi_app, role="ADMIN")

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        deps_mod.reset_graph_service()
        self.tmp.cleanup()

    def _sample(self, filename):
        with open(os.path.join(REPO_ROOT, "data", "sample", filename),
                  "rb") as fh:
            return fh.read()

    def test_full_pipeline(self):
        # 1-2. upload + validate
        upload = self.client.post(
            "/api/upload",
            files={"file": ("fir.csv", self._sample("fir.csv"),
                            "text/csv")},
            data={"dataset_type": "FIR"}).json()["data"]
        self.assertEqual(upload["status"], "UPLOADED")
        upload_id = upload["upload_id"]
        # 3-4. process (parse/normalize)
        proc = self.client.post("/api/process",
                                json={"upload_id": upload_id}).json()["data"]
        self.assertEqual(proc["status"], "SUCCEEDED")
        poll = self.client.get(f"/api/process/{proc['job_id']}")
        self.assertEqual(poll.json()["data"]["status"], "SUCCEEDED")
        # 5-6. NLP extract + resolve (canonical entities created)
        extracted = self.client.post(
            "/api/entities/extract",
            json={"upload_id": upload_id}).json()["data"]
        self.assertGreater(len(extracted["entities"]), 0)
        resolved = self.client.post("/api/entities/resolve", json={
            "document_id": upload_id,
            "entities": extracted["entities"]}).json()["data"]
        canonical_ids = {item["canonical_id"]
                         for item in resolved["resolved"]}
        self.assertGreater(len(canonical_ids), 0)
        # 7. Neo4j graph build + verify
        build = self.client.post("/api/graph/build",
                                 json={"upload_id": upload_id}).json()["data"]
        self.assertEqual(build["status"], "SUCCEEDED")
        self.assertTrue(build["verification"]["verified"])
        # 8-10. analytics + anomalies + priority
        run = self.client.post("/api/analytics/run", json={}).json()["data"]
        self.assertGreater(run["entities_scored"], 0)
        top_id = run["top"][0]["entity_id"]
        anomalies = self.client.get("/api/anomalies").json()["data"]
        self.assertGreater(len(anomalies["items"]), 0)
        pagerank = self.client.get(
            f"/api/analytics/pagerank?entity_id={top_id}").json()["data"]
        self.assertTrue(pagerank["items"])
        # 11. dashboard-facing reads over the same data
        entity = self.client.get(f"/api/entities/{top_id}").json()["data"]
        self.assertIsNotNone(entity["analytics_summary"])
        self.assertIsNotNone(entity["analytics_summary"]["priority_score"])
        graph = self.client.get(f"/api/graph/{top_id}").json()["data"]
        self.assertGreater(len(graph["nodes"]), 0)
        investigation = self.client.get(
            f"/api/investigation/{top_id}").json()["data"]
        self.assertIn("priority", investigation)
        self.assertIn("disclaimer", investigation["priority"])
        timeline = self.client.get(f"/api/timeline/{top_id}").json()["data"]
        self.assertIn("events", timeline)
        search = self.client.get(
            "/api/search",
            params={"q": entity["name"].split()[0]}).json()["data"]
        self.assertTrue(any(item["id"] == top_id
                            for item in search["items"]))
        # Provenance survived end to end.
        self.assertTrue(investigation["sources"])
        self.assertTrue(
            build["relationships_created"] + build["relationships_existing"]
            > 0)


if __name__ == "__main__":
    unittest.main()
