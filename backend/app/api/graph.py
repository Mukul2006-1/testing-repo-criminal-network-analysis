"""Phase 4 — entities + graph API (API_SPEC.md §§3-4).

- GET /api/entities[/{id}] reads canonical entities + mentions from the
  Phase 3 store (always available, no Neo4j required).
- GET /api/graph/{id}[/neighbors] and POST /api/graph/build require
  Neo4j and fail with structured 500/503 — never false success.
- No analytics/anomaly/dashboard endpoints (later phases).
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..schemas.graph import BuildRequest
from ..services import graph_queries as queries
from ..services import auth as auth_svc
from ..services.analytics import analytics_summary_for
from ..services.graph_builder import (
    build_from_upload,
    ensure_schema,
    verify_graph,
    write_graph,
)
from ..services.validation import IngestionError
from .deps import (
    error_response,
    get_graph_service,
    get_service,
    ok,
    processed_dir,
)

router = APIRouter()

ENTITY_TYPES = ("PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION",
                "DATE", "ACCOUNT")


def _entity_item(entity: dict, mentions: list[dict]) -> dict:
    aliases = sorted({m["text"] for m in mentions
                      if m["text"] != entity["canonical_name"]})
    confs = [m["confidence"] for m in mentions
             if m.get("confidence") is not None]
    return {
        "id": entity["id"], "type": entity["type"],
        "name": entity["canonical_name"], "aliases": aliases,
        "source_refs": [{"document_id": m["document_id"]}
                        for m in mentions],
        "confidence": max(confs) if confs else None,
    }


@router.get("/entities")
def list_entities(type: str | None = Query(None),
                  q: str | None = Query(None, max_length=128),
                  page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100),
                  sort: str = Query("name"),
                  order: str = Query("asc"),
                  user: dict = Depends(auth_svc.require_user)):
    if type is not None and type not in ENTITY_TYPES:
        return JSONResponse(
            status_code=422,
            content={"success": False,
                     "error": {"code": "INVALID_FILTER",
                               "message": f"type '{type}' is not allowed.",
                               "details": []}})
    if sort == "priority":
        return JSONResponse(
            status_code=422,
            content={"success": False,
                     "error": {"code": "NOT_IMPLEMENTED",
                               "message": "Priority sorting requires "
                                          "Phase 5 analytics.",
                               "details": []}})
    if sort not in ("name", "created_at") or order not in ("asc", "desc"):
        return JSONResponse(
            status_code=422,
            content={"success": False,
                     "error": {"code": "INVALID_FILTER",
                               "message": "sort must be name|created_at, "
                                          "order asc|desc.",
                               "details": []}})
    store = get_service().store
    types = [type] if type else list(ENTITY_TYPES)
    items = []
    for entity_type in types:
        for entity in store.list_entities_by_type(entity_type):
            mentions = store.list_mentions(entity["id"], limit=100)
            item = _entity_item(entity, mentions)
            if q and q.lower() not in item["name"].lower() and not any(
                    q.lower() in alias.lower()
                    for alias in item["aliases"]):
                continue
            items.append(item)
    reverse = order == "desc"
    items.sort(key=lambda i: (i["name"].lower(), i["id"]), reverse=reverse)
    total = len(items)
    start = (page - 1) * page_size
    return ok({"items": items[start:start + page_size],
               "pagination": {"page": page, "page_size": page_size,
                              "total": total,
                              "total_pages": (total + page_size - 1) //
                                             page_size}},
              "Entities retrieved.")


@router.get("/entities/{entity_id}")
def get_entity_detail(entity_id: str,
                      user: dict = Depends(auth_svc.require_user)):
    if len(entity_id) > 64:
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": {"code": "INVALID_ID",
                               "message": "Malformed entity id.",
                               "details": []}})
    store = get_service().store
    entity = store.get_entity(entity_id)
    if entity is None:
        return JSONResponse(
            status_code=404,
            content={"success": False,
                     "error": {"code": "NOT_FOUND",
                               "message": f"Unknown entity: {entity_id}",
                               "details": []}})
    mentions = store.list_mentions(entity_id, limit=100)
    item = _entity_item(entity, mentions)
    item["source_refs"] = [
        {"document_id": m["document_id"],
         "confidence": m.get("confidence")} for m in mentions]
    item["attributes"] = entity.get("attributes", {})
    item["analytics_summary"] = analytics_summary_for(store, entity_id)
    return ok(item, "Entity retrieved.")


def _graph_or_unavailable():
    try:
        service = get_graph_service()
        service.verify()
        return service, None
    except IngestionError as exc:
        return None, error_response(exc)


@router.get("/graph/{entity_id}")
def get_graph(entity_id: str, depth: int = Query(1),
              limit_nodes: int = Query(100), limit_edges: int = Query(300),
              user: dict = Depends(auth_svc.require_user)):
    service, error = _graph_or_unavailable()
    if error is not None:
        return error
    try:
        with service.session() as session:
            if queries.get_entity(session, entity_id) is None:
                return JSONResponse(
                    status_code=404,
                    content={"success": False,
                             "error": {"code": "NOT_FOUND",
                                       "message": f"Unknown entity: {entity_id}",
                                       "details": []}})
            data = queries.get_neighborhood(
                session, entity_id, depth=depth, limit_nodes=limit_nodes,
                limit_edges=limit_edges)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Graph retrieved.")


@router.get("/graph/{entity_id}/neighbors")
def get_neighbors(entity_id: str, depth: int = Query(1),
                  rel_types: str | None = Query(None),
                  node_types: str | None = Query(None),
                  limit_nodes: int = Query(100),
                  limit_edges: int = Query(300),
                  user: dict = Depends(auth_svc.require_user)):
    service, error = _graph_or_unavailable()
    if error is not None:
        return error
    try:
        parsed_rel = rel_types.split(",") if rel_types else None
        parsed_node = node_types.split(",") if node_types else None
        with service.session() as session:
            if queries.get_entity(session, entity_id) is None:
                return JSONResponse(
                    status_code=404,
                    content={"success": False,
                             "error": {"code": "NOT_FOUND",
                                       "message": f"Unknown entity: {entity_id}",
                                       "details": []}})
            data = queries.get_neighborhood(
                session, entity_id, depth=depth, rel_types=parsed_rel,
                node_types=parsed_node, limit_nodes=limit_nodes,
                limit_edges=limit_edges)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Neighbors retrieved.")


@router.post("/graph/build")
def build_graph(body: BuildRequest,
                user: dict = Depends(auth_svc.require_user)):
    """Full Phase 1-4 flow for one upload: extract -> resolve -> build ->
    verify. Connectivity is checked first so a dead Neo4j fails fast."""
    service, error = _graph_or_unavailable()
    if error is not None:
        return error
    try:
        store = get_service().store
        document = store.get_document(body.upload_id)
        if document is None:
            raise IngestionError("UPLOAD_NOT_FOUND",
                                 f"Unknown upload_id: {body.upload_id}",
                                 http_status=404)
        if document["status"] != "PROCESSED":
            raise IngestionError(
                "DOCUMENT_NOT_PROCESSED",
                f"Upload {body.upload_id} has status "
                f"{document['status']}; process it first.", http_status=422)
        path = os.path.join(processed_dir(), body.upload_id, "records.json")
        if not os.path.isfile(path):
            raise IngestionError("PROCESSING_FAILED",
                                 "Processed output is missing.",
                                 http_status=500)
        with open(path, encoding="utf-8") as fh:
            records = json.load(fh)
        nodes, relationships, notes = build_from_upload(
            store, body.upload_id, records)
        with service.session() as session:
            ensure_schema(session)
            counts = write_graph(session, nodes, relationships)
            verification = verify_graph(
                session,
                [n["props"]["id"] for n in nodes],
                [r["edge_id"] for r in relationships])
        data = {"upload_id": body.upload_id, **counts,
                "skipped_notes": notes["skipped"],
                "verification": verification}
    except IngestionError as exc:
        return error_response(exc)
    if not verification["verified"]:
        data["status"] = "PARTIAL"
        return JSONResponse(status_code=200, content={
            "success": True, "data": data,
            "message": "Graph written but verification found missing "
                       "elements; see verification."})
    data["status"] = "SUCCEEDED"
    return ok(data, f"Graph built: {counts['nodes_created']} new nodes, "
                    f"{counts['relationships_created']} new relationships.")
