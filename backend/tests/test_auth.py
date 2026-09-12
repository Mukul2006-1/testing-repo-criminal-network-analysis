"""Phase 6 tests — authentication, RBAC, search, timeline.

Covers password hashing, JWT lifecycle, login/logout/refresh, protected
endpoints (401), role restrictions (403), user administration, search and
timeline contracts. Isolated temp stores; repo data never touched.
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
from app.services import auth as auth_svc  # noqa: E402
from app.services.validation import IngestionError  # noqa: E402

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


class HashingTests(unittest.TestCase):
    def test_salted_unique_hashes(self):
        first = auth_svc.hash_password("Testpass123")
        second = auth_svc.hash_password("Testpass123")
        self.assertNotEqual(first, second)
        self.assertTrue(auth_svc.verify_password("Testpass123", first))
        self.assertTrue(auth_svc.verify_password("Testpass123", second))

    def test_wrong_password_rejected(self):
        hashed = auth_svc.hash_password("Testpass123")
        self.assertFalse(auth_svc.verify_password("Wrongpass123", hashed))
        self.assertFalse(auth_svc.verify_password("Testpass123", "garbage"))
        self.assertFalse(auth_svc.verify_password("Testpass123", ""))

    def test_policy_enforced(self):
        with self.assertRaises(IngestionError):
            auth_svc.hash_password("short")
        for bad_role in ("ROOT", "", "admin"):
            with self.assertRaises(IngestionError):
                auth_svc.validate_role(bad_role)
        self.assertEqual(auth_svc.validate_role("INVESTIGATOR"),
                         "INVESTIGATOR")


class JwtTests(unittest.TestCase):
    def setUp(self):
        os.environ["JWT_SECRET"] = "test-only-secret"

    def tearDown(self):
        os.environ.pop("JWT_SECRET", None)

    def test_roundtrip(self):
        token, expires_in = auth_svc.create_access_token("user_1",
                                                         "INVESTIGATOR")
        self.assertEqual(expires_in, 30 * 60)
        payload = auth_svc.decode_token(token, "access")
        self.assertEqual((payload["sub"], payload["role"]),
                         ("user_1", "INVESTIGATOR"))

    def test_wrong_secret_rejected(self):
        token, _ = auth_svc.create_access_token("user_1", "INVESTIGATOR")
        os.environ["JWT_SECRET"] = "other-secret"
        with self.assertRaises(IngestionError) as ctx:
            auth_svc.decode_token(token, "access")
        self.assertEqual(ctx.exception.http_status, 401)

    def test_expired_rejected(self):
        import jwt

        payload = {"sub": "user_1", "role": "INVESTIGATOR", "type": "access",
                   "iat": 1000, "exp": 1001}
        token = jwt.encode(payload, "test-only-secret", algorithm="HS256")
        with self.assertRaises(IngestionError):
            auth_svc.decode_token(token, "access")

    def test_wrong_type_rejected(self):
        refresh = auth_svc.create_refresh_token("user_1", "INVESTIGATOR")
        with self.assertRaises(IngestionError):
            auth_svc.decode_token(refresh, "access")

    def test_missing_secret_fails_closed(self):
        os.environ.pop("JWT_SECRET", None)
        with self.assertRaises(IngestionError) as ctx:
            auth_svc.create_access_token("user_1", "INVESTIGATOR")
        self.assertEqual(ctx.exception.http_status, 500)


def _load_sibling(name):
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class AuthApiTests(unittest.TestCase):
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

    def _seed(self, email, password, role, name="Test User"):
        self.store.create_user(
            {"id": f"user_{email.split('@')[0].replace('.', '')[:8]}",
             "name": name, "email": email,
             "password_hash": auth_svc.hash_password(password), "role": role,
             "created_at": _now(), "updated_at": _now()})
        return email

    def _login(self, email="admin@test.local", password="Testpass123"):
        return self.client.post("/api/auth/login",
                                json={"username": email, "password": password})

    def _token(self, email="admin@test.local", password="Testpass123"):
        return self._login(email, password).json()["data"]["access_token"]

    def _headers(self, email="admin@test.local", password="Testpass123"):
        return {"Authorization": f"Bearer {self._token(email, password)}"}

    def test_login_success_shape(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        resp = self._login()
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["token_type"], "Bearer")
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(data["user"]["role"], "ADMIN")
        self.assertNotIn("password_hash", resp.text)

    def test_login_no_enumeration(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        unknown = self.client.post(
            "/api/auth/login",
            json={"username": "nobody@test.local", "password": "Testpass123"})
        wrong = self.client.post(
            "/api/auth/login",
            json={"username": "admin@test.local", "password": "Wrongpass123"})
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json(), wrong.json())

    def test_missing_token_401(self):
        resp = self.client.get("/api/entities")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "UNAUTHENTICATED")

    def test_malformed_token_401(self):
        resp = self.client.get("/api/entities",
                               headers={"Authorization": "Bearer junk"})
        self.assertEqual(resp.status_code, 401)

    def test_expired_token_401(self):
        import jwt

        self._seed("admin@test.local", "Testpass123", "ADMIN")
        payload = {"sub": "user_admin", "role": "ADMIN", "type": "access",
                   "iat": 1000, "exp": 1001}
        token = jwt.encode(payload, "test-only-secret", algorithm="HS256")
        resp = self.client.get("/api/entities",
                               headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 401)

    def test_role_change_invalidates_token(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        self._seed("flex@test.local", "Testpass123", "INVESTIGATOR")
        headers = self._headers("flex@test.local")
        self.assertEqual(
            self.client.get("/api/entities", headers=headers).status_code,
            200)
        admin_headers = self._headers("admin@test.local")
        user_id = _store(self.tmp.name).get_user_by_email(
            "flex@test.local")["id"]
        self.client.patch(f"/api/users/{user_id}/role",
                          json={"role": "ADMIN"}, headers=admin_headers)
        resp = self.client.get("/api/entities", headers=headers)
        self.assertEqual(resp.status_code, 401)

    def test_rbac_investigator(self):
        self._seed("inv@test.local", "Testpass123", "INVESTIGATOR")
        headers = self._headers("inv@test.local")
        self.assertEqual(
            self.client.get("/api/entities", headers=headers).status_code,
            200)
        resp = self.client.post("/api/analytics/run", json={},
                                headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")
        self.assertEqual(
            self.client.get("/api/users", headers=headers).status_code, 403)
        self.assertEqual(
            self.client.post("/api/users",
                             json={"name": "X", "email": "x@t.local",
                                   "password": "Testpass123",
                                   "role": "INVESTIGATOR"},
                             headers=headers).status_code, 403)

    def test_rbac_senior(self):
        self._seed("senior@test.local", "Testpass123", "SENIOR_INVESTIGATOR")
        headers = self._headers("senior@test.local")
        self.assertEqual(
            self.client.get("/api/users", headers=headers).status_code, 403)
        # Senior may trigger analytics refresh only if Neo4j is reachable;
        # without it the failure must be 5xx (config/graph), never 403 (role).
        resp = self.client.post("/api/analytics/run", json={},
                                headers=headers)
        self.assertIn(resp.status_code, (200, 422, 500, 503))
        self.assertNotEqual(resp.status_code, 403)

    def test_admin_user_management(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        headers = self._headers("admin@test.local")
        created = self.client.post(
            "/api/users",
            json={"name": "Newbie", "email": "newbie@test.local",
                  "password": "Testpass123", "role": "INVESTIGATOR"},
            headers=headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertNotIn("password_hash", created.text)
        dup = self.client.post(
            "/api/users",
            json={"name": "Dup", "email": "NEWBIE@test.local",
                  "password": "Testpass123", "role": "INVESTIGATOR"},
            headers=headers)
        self.assertEqual(dup.status_code, 409)
        listing = self.client.get("/api/users", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn("password_hash", listing.text)
        user_id = created.json()["data"]["user"]["id"]
        patched = self.client.patch(f"/api/users/{user_id}/role",
                                    json={"role": "SENIOR_INVESTIGATOR"},
                                    headers=headers)
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["data"]["user"]["role"],
                         "SENIOR_INVESTIGATOR")
        bad_role = self.client.patch(f"/api/users/{user_id}/role",
                                     json={"role": "ROOT"}, headers=headers)
        self.assertEqual(bad_role.status_code, 422)
        missing = self.client.patch("/api/users/user_nope/role",
                                    json={"role": "ADMIN"}, headers=headers)
        self.assertEqual(missing.status_code, 404)

    def test_refresh_and_logout_and_me(self):
        self._seed("admin@test.local", "Testpass123", "ADMIN")
        login = self._login().json()["data"]
        refreshed = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": login["refresh_token"]})
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        headers = {"Authorization":
                   f"Bearer {refreshed.json()['data']['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["user"]["email"],
                         "admin@test.local")
        logout = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logout.status_code, 200)
        bad_refresh = self.client.post(
            "/api/auth/refresh", json={"refresh_token": "junk"})
        self.assertEqual(bad_refresh.status_code, 401)


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.client = make_authed_client(fastapi_app)
        store = _store(self.tmp.name)
        from app.services.entity_resolution import resolve_one

        resolve_one(store, "PERSON", "Rahul Sharma", "rahul sharma", 0.9,
                    "test", "FIR_001")
        resolve_one(store, "PHONE", "+919876543210", "+919876543210", 1.0,
                    "test", "CDR_001")

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.tmp.cleanup()

    def test_search_by_name(self):
        resp = self.client.get("/api/search", params={"q": "rahul"})
        self.assertEqual(resp.status_code, 200, resp.text)
        items = resp.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["match"], "name")

    def test_search_by_phone_and_id(self):
        resp = self.client.get("/api/search", params={"q": "9876543210"})
        self.assertTrue(any(item["type"] == "PHONE"
                            for item in resp.json()["data"]["items"]))

    def test_search_validation(self):
        self.assertEqual(self.client.get("/api/search").status_code, 400)
        self.assertEqual(self.client.get("/api/search",
                                         params={"q": "x"}).status_code, 400)
        self.assertEqual(self.client.get("/api/search",
                                         params={"q": "ab\x01"}).status_code,
                         422)

    def test_search_no_results(self):
        resp = self.client.get("/api/search", params={"q": "zzzznope"})
        self.assertEqual(resp.json()["data"]["items"], [])
        self.assertEqual(resp.json()["data"]["pagination"]["total"], 0)


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class TimelineApiTests(unittest.TestCase):
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
        from app.services.graph_builder import merge_node, merge_relationship

        FakeSession = _load_sibling("test_graph").FakeSession
        session = FakeSession(self.driver.store, self.driver.calls)
        merge_node(session, "Person",
                   {"id": "person_001", "name": "Rahul Sharma",
                    "normalized_name": "rahul sharma", "risk_score": 0.0})
        merge_node(session, "Person",
                   {"id": "person_002", "name": "Amit Kumar",
                    "normalized_name": "amit kumar", "risk_score": 0.0})
        merge_relationship(session, "Person", "person_001", "CALLED",
                           "Person", "person_002", "rel_1",
                           {"timestamp": "2026-08-12T10:32:00Z",
                            "source_record_id": "CDR_001"})
        merge_relationship(session, "Person", "person_002", "CALLED",
                           "Person", "person_001", "rel_2",
                           {"timestamp": "2026-08-10T09:00:00Z",
                            "source_record_id": "CDR_002"})

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        deps_mod.reset_graph_service()
        self.tmp.cleanup()

    def test_timeline_order_and_shape(self):
        resp = self.client.get("/api/timeline/person_001")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["entity_id"], "person_001")
        self.assertEqual(len(data["events"]), 2)
        self.assertLessEqual(data["events"][0]["timestamp"],
                             data["events"][1]["timestamp"])
        event = data["events"][0]
        for key in ("timestamp", "type", "description", "source_id"):
            self.assertIn(key, event)
        self.assertEqual(event["type"], "CALL")

    def test_timeline_filters(self):
        resp = self.client.get("/api/timeline/person_001?types=CALL"
                               "&from=2026-08-11T00:00:00Z")
        events = resp.json()["data"]["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_id"], "CDR_001")
        bad = self.client.get("/api/timeline/person_001?types=BOGUS")
        self.assertEqual(bad.status_code, 422)

    def test_timeline_unknown(self):
        self.assertEqual(
            self.client.get("/api/timeline/ghost").status_code, 404)


if __name__ == "__main__":
    unittest.main()
