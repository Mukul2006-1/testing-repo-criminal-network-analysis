"""Phase 5 — analytics/anomaly/investigation API.

- POST /api/analytics/run executes one scoring run (Neo4j required).
- GET analytics/anomaly endpoints serve stored results (no Neo4j needed
  after a run) with the API_SPEC.md shapes, pagination, and disclaimer.
- GET /api/investigation/{id} aggregates the §9 summary.
- No dashboard/UI work; no criminality language anywhere.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..services import analytics as analytics_mod
from ..services import graph_queries as queries
from ..services import scoring as scoring_mod
from ..services import auth as auth_svc
from ..services.validation import IngestionError
from .deps import (
    error_response,
    get_graph_service,
    get_service,
    ok,
    processed_dir,
)
from .graph import _entity_item

router = APIRouter()

DISCLAIMER = "Analytical signal only — not evidence of guilt."

EVENT_TYPES = {"CALLED": "CALL", "MET": "MEETING",
               "TRANSFERRED_TO": "TRANSACTION", "LOCATED_AT": "LOCATION",
               "TRAVELLED_TO": "TRAVEL", "MENTIONED_IN": "FIR",
               "USED": "VEHICLE", "OWNS": "VEHICLE"}


def _not_found(entity_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"success": False,
                 "error": {"code": "NOT_FOUND",
                           "message": f"Unknown entity: {entity_id}",
                           "details": []}})


def _paginate(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size],
            "pagination": {"page": page, "page_size": page_size,
                           "total": total,
                           "total_pages": (total + page_size - 1) //
                                          page_size}}


def _records_for_run(store, upload_id: str | None) -> list[tuple[str, list]]:
    """Load processed records for one upload, or every PROCESSED upload."""
    if upload_id is not None:
        document = store.get_document(upload_id)
        if document is None:
            raise IngestionError("UPLOAD_NOT_FOUND",
                                 f"Unknown upload_id: {upload_id}",
                                 http_status=404)
        uploads = [upload_id] if document["status"] == "PROCESSED" else []
        if not uploads:
            raise IngestionError(
                "DOCUMENT_NOT_PROCESSED",
                f"Upload {upload_id} has status {document['status']}.",
                http_status=422)
    else:
        uploads = []
        for filename in sorted(os.listdir(processed_dir())):
            directory = os.path.join(processed_dir(), filename)
            if not os.path.isdir(directory):
                continue
            document = store.get_document(filename)
            if document is not None and document["status"] == "PROCESSED":
                uploads.append(filename)
    record_files = []
    for uid in uploads:
        path = os.path.join(processed_dir(), uid, "records.json")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            record_files.append((uid, json.load(fh)))
    if not record_files:
        raise IngestionError("NO_PROCESSED_DATA",
                             "No processed records available for scoring.",
                             http_status=422)
    return record_files


@router.post("/analytics/run")
def run(body: dict | None = None,
        user: dict = Depends(auth_svc.require_senior)):
    """Execute one analytics+anomaly+scoring run. Neo4j required."""
    try:
        service = get_graph_service()
        service.verify()
    except IngestionError as exc:
        return error_response(exc)
    try:
        upload_id = (body or {}).get("upload_id")
        store = get_service().store
        with service.session() as session:
            snapshot = queries.fetch_graph(session)
        nodes = [{"id": node["id"]} for node in snapshot["nodes"]]
        edges = [(edge["source"], edge["target"])
                 for edge in snapshot["edges"]]
        record_files = _records_for_run(store, upload_id)
        summary = analytics_mod.run_analytics(store, nodes, edges,
                                              record_files)
        summary["graph_truncated"] = snapshot["truncated"]
    except IngestionError as exc:
        return error_response(exc)
    summary["disclaimer"] = DISCLAIMER
    return ok(summary, f"Scored {summary['entities_scored']} entities "
                       f"(run {summary['run_id']}).")


def _analytics_items(metric: str, entity_id: str | None,
                     community_id: int | None, page: int,
                     page_size: int) -> dict:
    store = get_service().store
    if entity_id is not None:
        row = store.get_analytics(entity_id)
        if row is None:
            raise IngestionError("NOT_FOUND",
                                 f"No analytics for entity: {entity_id}",
                                 http_status=404)
        rows = [row]
    elif community_id is not None:
        rows = store.list_analytics(community_id=community_id)
    else:
        rows = store.list_analytics()
    items = [{"entity_id": row["entity_id"], "degree": row["degree"],
              "pagerank": row["pagerank"], "betweenness": row["betweenness"],
              "community_id": row["community_id"]} for row in rows]
    if metric in ("pagerank", "betweenness", "degree"):
        items.sort(key=lambda item: (-item[metric], item["entity_id"]))
    return {**_paginate(items, page, page_size), "disclaimer": DISCLAIMER}


@router.get("/analytics/pagerank")
def get_pagerank(entity_id: str | None = Query(None),
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100),
                 user: dict = Depends(auth_svc.require_user)):
    try:
        data = _analytics_items("pagerank", entity_id, None, page, page_size)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Analytics retrieved.")


@router.get("/analytics/betweenness")
def get_betweenness(entity_id: str | None = Query(None),
                    page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100),
                    user: dict = Depends(auth_svc.require_user)):
    try:
        data = _analytics_items("betweenness", entity_id, None, page,
                                page_size)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Analytics retrieved.")


@router.get("/analytics/communities")
def get_communities(community_id: int | None = Query(None),
                    page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100),
                    user: dict = Depends(auth_svc.require_user)):
    try:
        data = _analytics_items("communities", None, community_id, page,
                                page_size)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Analytics retrieved.")


@router.get("/analytics/degree")
def get_degree(entity_id: str | None = Query(None),
               page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100),
               user: dict = Depends(auth_svc.require_user)):
    try:
        data = _analytics_items("degree", entity_id, None, page, page_size)
    except IngestionError as exc:
        return error_response(exc)
    return ok(data, "Analytics retrieved.")


@router.get("/anomalies")
def list_anomalies(entity_id: str | None = Query(None),
                   severity: str | None = Query(None),
                   min_score: float | None = Query(None, ge=0.0, le=1.0),
                   page: int = Query(1, ge=1),
                   page_size: int = Query(20, ge=1, le=100),
                   user: dict = Depends(auth_svc.require_user)):
    if severity is not None and severity not in ("LOW", "MEDIUM", "HIGH"):
        return JSONResponse(
            status_code=422,
            content={"success": False,
                     "error": {"code": "INVALID_FILTER",
                               "message": "severity must be LOW|MEDIUM|HIGH.",
                               "details": []}})
    store = get_service().store
    if entity_id is not None:
        row = store.latest_anomaly(entity_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"success": False,
                         "error": {"code": "NOT_FOUND",
                                   "message": "No anomaly for entity: "
                                              f"{entity_id}",
                                   "details": []}})
        rows = [row]
    else:
        rows = store.list_anomalies()
    items = []
    for row in rows:
        if severity is not None and row["severity"] != severity:
            continue
        if min_score is not None and float(row["score"]) < min_score:
            continue
        items.append({"entity_id": row["entity_id"],
                      "features": row["features"],
                      "anomaly_score": row["score"],
                      "severity": row["severity"],
                      "reasons": row["reason"].split("; ") if row["reason"]
                      else []})
    return ok({**_paginate(items, page, page_size), "disclaimer": DISCLAIMER},
              "Anomalies retrieved.")


def _timeline_events(service, entity, limit: int = 100) -> list[dict]:
    """Chronological sourced events from graph edges (no invention)."""
    with service.session() as session:
        neighborhood = queries.get_neighborhood(
            session, entity["id"], depth=1, limit_nodes=500, limit_edges=500)
    labels = {node["id"]: node["label"] for node in neighborhood["nodes"]}
    events = []
    for edge in neighborhood["edges"]:
        event_type = EVENT_TYPES.get(edge["type"])
        timestamp = (edge.get("metadata") or {}).get("timestamp")
        source = (edge.get("metadata") or {}).get("source_record")
        if event_type is None or timestamp is None or source is None:
            continue
        other = edge["target"] if edge["source"] == entity["id"] \
            else edge["source"]
        events.append({
            "timestamp": timestamp, "type": event_type,
            "description": f"{entity['canonical_name']} —{edge['type']}→ "
                           f"{labels.get(other, other)}",
            "source_id": source})
    events.sort(key=lambda event: event["timestamp"])
    return events[:limit]


@router.get("/investigation/{entity_id}")
def get_investigation(entity_id: str,
                      user: dict = Depends(auth_svc.require_user)):
    """API_SPEC.md §9 summary: priority, metrics, anomaly, explanations,
    timeline reference, key relationships, sources."""
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
        return _not_found(entity_id)
    summary = analytics_mod.analytics_summary_for(store, entity_id) or {
        "degree": 0, "pagerank": 0.0, "betweenness": 0.0,
        "community_id": None, "anomaly_score": 0.0, "priority_score": 0.0}
    priority = scoring_mod.priority_score(
        summary["pagerank"], summary["betweenness"],
        summary["anomaly_score"])
    anomaly = store.latest_anomaly(entity_id)
    explanations = list(priority["reasons"])
    if anomaly is not None:
        explanations.extend(f"Anomaly evidence: {reason}"
                            for reason in anomaly["reason"].split("; ")
                            if reason and reason != "No anomaly signal")
    key_relationships, sources, events = [], [], []
    try:
        service = get_graph_service()
        service.verify()
        with service.session() as session:
            neighborhood = queries.get_neighborhood(
                session, entity_id, depth=1, limit_nodes=50, limit_edges=50)
        key_relationships = [
            {"id": edge["id"], "source": edge["source"],
             "target": edge["target"], "type": edge["type"]}
            for edge in neighborhood["edges"][:10]]
        events = _timeline_events(service, entity)
    except IngestionError:
        pass  # graph-dependent sections stay empty without Neo4j
    mentions = store.list_mentions(entity_id, limit=100)
    sources = [{"document_id": mention["document_id"]}
               for mention in mentions]
    return ok({
        "entity": {"id": entity["id"], "type": entity["type"],
                   "name": entity["canonical_name"]},
        "priority": {
            "score": priority["score"],
            "formula": scoring_mod.FORMULA,
            "formula_version": scoring_mod.FORMULA_VERSION,
            "components": priority["components"],
            "disclaimer": scoring_mod.DISCLAIMER},
        "graph_metrics": {"pagerank": summary["pagerank"],
                          "betweenness": summary["betweenness"],
                          "community_id": summary["community_id"]},
        "anomaly": {"anomaly_score": summary["anomaly_score"],
                    "severity": (anomaly["severity"] if anomaly else "LOW"),
                    "reasons": (anomaly["reason"].split("; ")
                                if anomaly else [])},
        "explanations": explanations,
        "timeline_ref": f"/api/timeline/{entity_id}",
        "timeline": events,
        "key_relationships": key_relationships,
        "sources": sources}, "Investigation summary retrieved.")
