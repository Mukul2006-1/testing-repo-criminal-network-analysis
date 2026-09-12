"""Phase 6 — GET /api/timeline/{id} (API_SPEC.md §7).

Chronological sourced events derived from the entity's graph
relationships (edge timestamps + source records). Requires Neo4j, like
the other graph endpoints. No invented events: edges without both a
timestamp and a source record are skipped.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..services import auth as auth_svc
from ..services import graph_queries as queries
from ..services.validation import IngestionError
from .analytics import EVENT_TYPES
from .deps import error_response, get_graph_service, ok

router = APIRouter()


@router.get("/timeline/{entity_id}")
def get_timeline(
    entity_id: str,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    types: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(auth_svc.require_user),
):
    try:
        service = get_graph_service()
        service.verify()
    except IngestionError as exc:
        return error_response(exc)
    wanted = None
    if types is not None:
        wanted = set(types.split(","))
        unknown = wanted - set(EVENT_TYPES.values())
        if unknown:
            return JSONResponse(
                status_code=422,
                content={"success": False,
                         "error": {"code": "INVALID_FILTER",
                                   "message": f"Unknown event types: "
                                              f"{sorted(unknown)}.",
                                   "details": []}})
    try:
        with service.session() as session:
            if queries.get_entity(session, entity_id) is None:
                return JSONResponse(
                    status_code=404,
                    content={"success": False,
                             "error": {"code": "NOT_FOUND",
                                       "message": f"Unknown entity: {entity_id}",
                                       "details": []}})
            neighborhood = queries.get_neighborhood(
                session, entity_id, depth=1, limit_nodes=500,
                limit_edges=1500)
    except IngestionError as exc:
        return error_response(exc)
    labels = {node["id"]: node["label"] for node in neighborhood["nodes"]}
    name = labels.get(entity_id, entity_id)
    events = []
    for edge in neighborhood["edges"]:
        event_type = EVENT_TYPES.get(edge["type"])
        timestamp = (edge.get("metadata") or {}).get("timestamp")
        source = (edge.get("metadata") or {}).get("source_record")
        if event_type is None or timestamp is None or source is None:
            continue
        if wanted is not None and event_type not in wanted:
            continue
        if from_ is not None and timestamp < from_:
            continue
        if to is not None and timestamp > to:
            continue
        other = edge["target"] if edge["source"] == entity_id \
            else edge["source"]
        events.append({
            "timestamp": timestamp, "type": event_type,
            "description": f"{name} —{edge['type']}→ "
                           f"{labels.get(other, other)}",
            "source_id": source})
    events.sort(key=lambda event: event["timestamp"])
    total = len(events)
    start = (page - 1) * page_size
    return ok({"entity_id": entity_id,
               "events": events[start:start + page_size],
               "pagination": {"page": page, "page_size": page_size,
                              "total": total,
                              "total_pages": (total + page_size - 1) //
                                             page_size}},
              "Timeline retrieved.")
