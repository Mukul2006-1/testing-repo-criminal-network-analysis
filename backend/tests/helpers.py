"""Shared API-test helpers: isolated env, admin seeding, authed client.

Every API test class uses these so Phase 6 authentication is exercised
without touching repo data. Service-level (stdlib) tests are unaffected.
"""

import datetime
import os
import sys
import uuid

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

TEST_JWT_SECRET = "test-only-secret-0123456789abcdef"
TEST_PASSWORD = "Testpass123"


def configure_test_env(tmpdir, jwt_secret=TEST_JWT_SECRET):
    os.environ["RAW_DATA_DIR"] = os.path.join(tmpdir, "raw")
    os.environ["PROCESSED_DATA_DIR"] = os.path.join(tmpdir, "processed")
    os.environ["DOCUMENT_DB_PATH"] = os.path.join(tmpdir, "docs.db")
    os.environ["JWT_SECRET"] = jwt_secret


def clear_test_env():
    for var in ("RAW_DATA_DIR", "PROCESSED_DATA_DIR", "DOCUMENT_DB_PATH",
                "JWT_SECRET"):
        os.environ.pop(var, None)


def seed_token(role="ADMIN", email=None):
    """Create a user directly in the test store; return a live JWT."""
    from app.database.documents import DocumentStore
    from app.services import auth as auth_svc

    store = DocumentStore(os.environ["DOCUMENT_DB_PATH"])
    email = email or f"{role.lower()}-{uuid.uuid4().hex[:6]}@test.local"
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    store.create_user({"id": user_id, "name": f"Test {role}",
                       "email": email,
                       "password_hash": auth_svc.hash_password(TEST_PASSWORD),
                       "role": role, "created_at": now, "updated_at": now})
    token, _ = auth_svc.create_access_token(user_id, role)
    return token


class AuthedClient:
    """TestClient wrapper injecting Authorization on every request."""

    def __init__(self, client, token):
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"}

    def _merge(self, kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", self._headers["Authorization"])
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._merge(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._merge(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._merge(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._merge(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._merge(kwargs))

    def __getattr__(self, name):
        return getattr(self._client, name)


def make_authed_client(app, role="ADMIN"):
    from fastapi.testclient import TestClient

    return AuthedClient(TestClient(app), seed_token(role))
