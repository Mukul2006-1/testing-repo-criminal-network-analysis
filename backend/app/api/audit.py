"""Audit trail API: verify the hash chain, browse entries (API_SPEC §audit).

Additive read-only endpoints; no existing contract is changed. Entries are
written by the upload/process/graph/analytics/auth layers on success.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..services import audit as audit_mod
from ..services import auth as auth_svc
from .deps import get_service, ok

router = APIRouter()


@router.get("/audit/verify")
def verify_chain(user: dict = Depends(auth_svc.require_user)):
    """Recompute the tamper-evident chain and report its integrity."""
    result = audit_mod.verify(get_service().store)
    message = (f"Audit chain verified ({result['count']} events)."
               if result["verified"] else
               f"Audit chain BROKEN at {result['broken_at']}.")
    return ok(result, message)


@router.get("/audit/entries")
def list_entries(user: dict = Depends(auth_svc.require_user),
                 page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=200)):
    """Paginated audit events, oldest first. Hashes only — no secrets."""
    store = get_service().store
    entries = store.list_audit(limit=page * page_size)
    total = store.count_audit()
    start = (page - 1) * page_size
    items = [{
        "id": e["id"], "created_at": e["created_at"], "actor": e["actor"],
        "action": e["action"], "target": e["target"],
        "input_hash": e["input_hash"], "output_hash": e["output_hash"],
        "prev_hash": e["prev_hash"], "hash": e["hash"],
    } for e in entries[start:start + page_size]]
    return ok({"items": items,
               "pagination": {"page": page, "page_size": page_size,
                              "total": total,
                              "total_pages": (total + page_size - 1) //
                                             page_size}},
              "Audit entries retrieved.")
