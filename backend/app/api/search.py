"""Phase 6 — GET /api/search (API_SPEC.md §8).

Substring search over canonical entity names, aliases and IDs from the
Phase 3 store (no Neo4j required, no full-document grep). Query is
length-capped and matched literally (no regex from the client).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..services import auth as auth_svc
from .deps import get_service, ok

router = APIRouter()


@router.get("/search")
def search(q: str | None = Query(None, max_length=128),
           page: int = Query(1, ge=1),
           page_size: int = Query(20, ge=1, le=50),
           user: dict = Depends(auth_svc.require_user)):
    if q is None or len(q.strip()) < 2:
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": {"code": "INVALID_QUERY",
                               "message": "Query must be at least 2 characters.",
                               "details": []}})
    needle = q.strip()
    lowered = needle.lower()
    if any(ord(char) < 32 for char in needle):
        return JSONResponse(
            status_code=422,
            content={"success": False,
                     "error": {"code": "INVALID_QUERY",
                               "message": "Query contains control characters.",
                               "details": []}})
    store = get_service().store
    items = []
    for entity_type in ("PERSON", "PHONE", "LOCATION", "VEHICLE",
                        "ORGANIZATION", "DATE", "ACCOUNT"):
        for entity in store.list_entities_by_type(entity_type):
            mentions = store.list_mentions(entity["id"], limit=100)
            if lowered in entity["canonical_name"].lower() or \
                    lowered in entity["id"].lower():
                match = "name" if lowered in entity["canonical_name"].lower() \
                    else "id"
            elif any(lowered in mention["text"].lower()
                     for mention in mentions):
                match = "alias"
            else:
                continue
            items.append({"id": entity["id"], "type": entity["type"],
                          "name": entity["canonical_name"], "match": match})
    items.sort(key=lambda item: (item["name"].lower(), item["id"]))
    total = len(items)
    start = (page - 1) * page_size
    return ok({"items": items[start:start + page_size],
               "pagination": {"page": page, "page_size": page_size,
                              "total": total,
                              "total_pages": (total + page_size - 1) //
                                             page_size}},
              "Search complete.")
