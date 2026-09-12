"""Phase 6 — authentication & authorization (stdlib + PyJWT).

Local JWT-based auth per API_SPEC.md §10:

- Passwords: PBKDF2-HMAC-SHA256 (600k iterations, 16-byte salt, stdlib
  hashlib — no extra dependency, NIST-approved KDF). Stored format:
  ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``. Plaintext never
  persisted, logged, or returned.
- Tokens: HS256 access (30 min) + refresh (7 days) JWTs with
  ``sub`` (user id), ``role``, ``type`` claims. ``JWT_SECRET`` env is
  required — missing secret fails closed (500), never a fallback key.
- Roles are validated server-side on every request via FastAPI
  dependencies. Frontend-supplied roles are never trusted.

Capabilities (API_SPEC.md §10 matrix):

- INVESTIGATOR: upload/process, read entities/graph/timeline/search/
  anomalies, investigation reports.
- SENIOR_INVESTIGATOR: + analytics refresh, investigation management.
- ADMIN: + user/role administration.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .validation import IngestionError

_auth_store_override = None


def set_auth_store_override(store) -> None:
    """Test hook: point auth at an isolated store."""
    global _auth_store_override
    _auth_store_override = store


def reset_auth_store_override() -> None:
    global _auth_store_override
    _auth_store_override = None


def _auth_store():
    if _auth_store_override is not None:
        return _auth_store_override
    from ..database.documents import DocumentStore, default_db_path
    import os as _os

    return DocumentStore(_os.environ.get("DOCUMENT_DB_PATH",
                                         default_db_path()))

ROLES = ("INVESTIGATOR", "SENIOR_INVESTIGATOR", "ADMIN")
ALL_ROLES = ROLES
SENIOR_ROLES = ("SENIOR_INVESTIGATOR", "ADMIN")
ADMIN_ROLES = ("ADMIN",)

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 7
MIN_PASSWORD_LENGTH = 8
_PBKDF2_ITERATIONS = 600_000

_bearer = HTTPBearer(auto_error=False)


def validate_password_policy(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise IngestionError(
            "INVALID_PASSWORD",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            http_status=422)


def validate_role(role: str) -> str:
    if role not in ROLES:
        raise IngestionError(
            "INVALID_ROLE", f"Role must be one of {list(ROLES)}.",
            http_status=422)
    return role


def hash_password(password: str) -> str:
    validate_password_policy(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 _PBKDF2_ITERATIONS)
    return (f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
            f"{salt.hex()}${digest.hex()}")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = password_hash.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
            int(iterations))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError, AttributeError):
        return False


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise IngestionError(
            "AUTH_CONFIG_ERROR",
            "JWT_SECRET is not set. Set a local-only secret (never commit).",
            http_status=500)
    return secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(user_id: str, role: str, token_type: str,
                 expires: timedelta) -> str:
    import jwt

    issued = _now()
    return jwt.encode(
        {"sub": user_id, "role": role, "type": token_type,
         "iat": int(issued.timestamp()),
         "exp": int((issued + expires).timestamp())},
        get_jwt_secret(), algorithm="HS256")


def create_access_token(user_id: str, role: str) -> tuple[str, int]:
    return (create_token(user_id, role, "access",
                         timedelta(minutes=ACCESS_TOKEN_MINUTES)),
            ACCESS_TOKEN_MINUTES * 60)


def create_refresh_token(user_id: str, role: str) -> str:
    return create_token(user_id, role, "refresh",
                        timedelta(days=REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str = "access") -> dict:
    import jwt

    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except Exception as exc:
        raise IngestionError("UNAUTHENTICATED",
                             "Invalid or expired token.",
                             http_status=401) from exc
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise IngestionError("UNAUTHENTICATED",
                             "Invalid or expired token.", http_status=401)
    return payload


def public_user(row: dict) -> dict:
    """API-safe user shape. The password hash never leaves the server."""
    return {"id": row["id"], "name": row["name"], "email": row["email"],
            "role": row["role"]}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise IngestionError("UNAUTHENTICATED",
                             "Authentication required.", http_status=401)
    payload = decode_token(credentials.credentials, "access")
    row = _auth_store().get_user_by_id(payload["sub"])
    if row is None:
        raise IngestionError("UNAUTHENTICATED",
                             "Authentication required.", http_status=401)
    if row["role"] != payload.get("role"):
        # Role changed since issuance: stale token, re-login required.
        raise IngestionError("UNAUTHENTICATED",
                             "Role changed; please log in again.",
                             http_status=401)
    return public_user(row)


def require_roles(*allowed: str):
    """FastAPI dependency factory enforcing server-side RBAC."""

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise IngestionError(
                "FORBIDDEN",
                "Insufficient role for this operation.", http_status=403)
        return user

    return checker


require_user = require_roles(*ALL_ROLES)
require_senior = require_roles(*SENIOR_ROLES)
require_admin = require_roles(*ADMIN_ROLES)
