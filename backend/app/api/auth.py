"""Phase 6 — authentication & user administration (API_SPEC.md §10).

- POST /api/auth/login|refresh|logout, GET /api/auth/me
- POST /api/users, GET /api/users, PATCH /api/users/{id}/role (ADMIN only)

Login failures always return the same generic 401 (no user enumeration).
User payloads never contain password hashes. Logout is client-side token
discard (stateless JWT); documented in README.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    RefreshRequest,
    SetRoleRequest,
)
from ..services import auth as auth_svc
from ..services.validation import IngestionError
from .deps import error_response, get_service, ok

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _invalid_credentials() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"success": False,
                 "error": {"code": "INVALID_CREDENTIALS",
                           "message": "Invalid username or password.",
                           "details": []}})


@router.post("/auth/login")
def login(body: LoginRequest):
    store = get_service().store
    row = store.get_user_by_email(body.username)
    if row is None or not auth_svc.verify_password(body.password,
                                                   row["password_hash"]):
        return _invalid_credentials()
    token, expires_in = auth_svc.create_access_token(row["id"], row["role"])
    return ok({"access_token": token, "token_type": "Bearer",
               "expires_in": expires_in,
               "refresh_token": auth_svc.create_refresh_token(row["id"],
                                                              row["role"]),
               "user": auth_svc.public_user(row)}, "Login successful.")


@router.post("/auth/refresh")
def refresh(body: RefreshRequest):
    try:
        payload = auth_svc.decode_token(body.refresh_token, "refresh")
    except IngestionError:
        return _invalid_credentials()
    store = get_service().store
    row = store.get_user_by_id(payload["sub"])
    if row is None or row["role"] != payload.get("role"):
        return _invalid_credentials()
    token, expires_in = auth_svc.create_access_token(row["id"], row["role"])
    return ok({"access_token": token, "token_type": "Bearer",
               "expires_in": expires_in}, "Token refreshed.")


@router.post("/auth/logout")
def logout(user: dict = Depends(auth_svc.require_user)):
    return ok({"user_id": user["id"]},
              "Logged out. Discard tokens client-side.")


@router.get("/auth/me")
def me(user: dict = Depends(auth_svc.require_user)):
    return ok({"user": user}, "Current user.")


def _create_user(store, name: str, email: str, password: str,
                 role: str) -> dict:
    auth_svc.validate_role(role)
    email = email.strip().lower()
    if "@" not in email:
        raise IngestionError("INVALID_EMAIL",
                             "Email address is not valid.",
                             http_status=422)
    user = {"id": f"user_{uuid.uuid4().hex[:8]}", "name": name.strip(),
            "email": email, "password_hash": auth_svc.hash_password(password),
            "role": role, "created_at": _now(), "updated_at": _now()}
    try:
        store.create_user(user)
    except sqlite3.IntegrityError as exc:
        raise IngestionError("DUPLICATE_EMAIL",
                             "Email is already registered.",
                             http_status=409) from exc
    return auth_svc.public_user(user)


@router.post("/users", status_code=201)
def create_user(body: CreateUserRequest,
                admin: dict = Depends(auth_svc.require_admin)):
    try:
        user = _create_user(get_service().store, body.name, body.email,
                            body.password, body.role.strip().upper())
    except IngestionError as exc:
        return error_response(exc)
    return ok({"user": user}, "User created.", status_code=201)


@router.get("/users")
def list_users(admin: dict = Depends(auth_svc.require_admin)):
    users = [auth_svc.public_user(row)
             for row in get_service().store.list_users()]
    return ok({"items": users, "total": len(users)}, "Users retrieved.")


@router.patch("/users/{user_id}/role")
def set_role(user_id: str, body: SetRoleRequest,
             admin: dict = Depends(auth_svc.require_admin)):
    store = get_service().store
    if store.get_user_by_id(user_id) is None:
        return JSONResponse(
            status_code=404,
            content={"success": False,
                     "error": {"code": "NOT_FOUND",
                               "message": f"Unknown user: {user_id}",
                               "details": []}})
    try:
        auth_svc.validate_role(body.role.strip().upper())
        store.set_user_role(user_id, body.role.strip().upper())
    except IngestionError as exc:
        return error_response(exc)
    return ok({"user": auth_svc.public_user(store.get_user_by_id(user_id))},
              "Role updated.")
