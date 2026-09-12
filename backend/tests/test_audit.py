"""Audit-trail tests — hash chain, tamper detection, API surface.

Tamper-evident SHA-256 chain per PROJECT_SPEC.md §17. Isolated temp
stores; repo data never touched.
"""

import datetime
import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.documents import DocumentStore  # noqa: E402
from app.services import audit as audit_mod  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:
    HAS_API = False


def _store(tmpdir):
    return DocumentStore(os.path.join(tmpdir, "docs.db"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = _store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_chain_verifies(self):
        result = audit_mod.verify(self.store)
        self.assertTrue(result["verified"])
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["head_hash"])

    def test_append_links_hashes(self):
        first = audit_mod.record(self.store, actor="a@t.local",
                                 action="ingest.upload", target="upl_1",
                                 input_hash="abc")
        second = audit_mod.record(self.store, actor="a@t.local",
                                  action="ingest.process", target="upl_1")
        self.assertEqual(first["prev_hash"], "GENESIS")
        self.assertEqual(second["prev_hash"], first["hash"])
        result = audit_mod.verify(self.store)
        self.assertTrue(result["verified"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["head_hash"], second["hash"])

    def test_tamper_detected(self):
        audit_mod.record(self.store, actor="a@t.local", action="auth.login")
        audit_mod.record(self.store, actor="a@t.local", action="graph.build")
        with self.store._session() as conn:
            conn.execute("UPDATE audit_logs SET action = 'evil' WHERE "
                         "rowid = 1")
        result = audit_mod.verify(self.store)
        self.assertFalse(result["verified"])
        self.assertIsNotNone(result["broken_at"])

    def test_deletion_detected(self):
        first = audit_mod.record(self.store, actor="a@t.local",
                                 action="auth.login")
        audit_mod.record(self.store, actor="a@t.local", action="graph.build")
        with self.store._session() as conn:
            conn.execute("DELETE FROM audit_logs WHERE id = ?",
                         (first["id"],))
        result = audit_mod.verify(self.store)
        self.assertFalse(result["verified"])

    def test_missing_actor_rejected(self):
        from app.services.validation import IngestionError

        with self.assertRaises(IngestionError):
            audit_mod.record(self.store, actor="", action="auth.login")


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class AuditApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.client = TestClient(fastapi_app)
        self.store = _store(self.tmp.name)

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.tmp.cleanup()

    def _seed(self, email, password, role):
        self.store.create_user(
            {"id": f"user_{email.split('@')[0].replace('.', '')[:8]}",
             "name": "Audit User", "email": email,
             "password_hash": auth_svc.hash_password(password), "role": role,
             "created_at": _now(), "updated_at": _now()})

    def _headers(self, email="admin@test.local", password="Testpass123"):
        resp = self.client.post("/api/auth/login",
                               json={"username": email, "password": password})
        self.assertEqual(resp.status_code, 200, resp.text)
        return {"Authorization":
                f"Bearer {resp.json()['data']['access_token']}"}

    def test_login_emits_audit_event(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        self.client.post("/api/auth/login",
                         json={"username": "admin@test.local",
                               "password": "Testpass123"})
        entries = self.store.list_audit()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "auth.login")
        self.assertEqual(entries[0]["actor"], "admin@test.local")

    def test_verify_endpoint(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        headers = self._headers()
        resp = self.client.get("/api/audit/verify", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertTrue(data["verified"])
        self.assertGreaterEqual(data["count"], 1)
        self.assertIsNotNone(data["head_hash"])

    def test_entries_endpoint_shape(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        headers = self._headers()
        resp = self.client.get("/api/audit/entries", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertIn("items", data)
        self.assertIn("pagination", data)
        self.assertNotIn("password_hash", resp.text)
        self.assertNotIn("access_token", resp.text)

    def test_unauthenticated_rejected(self):
        self.assertEqual(self.client.get("/api/audit/verify").status_code,
                         401)
        self.assertEqual(self.client.get("/api/audit/entries").status_code,
                         401)


if __name__ == "__main__":
    unittest.main()
