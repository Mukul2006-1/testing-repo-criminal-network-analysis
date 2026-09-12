"""Phase 2 — shared API wiring (envelope, errors, service factory).

Auth/RBAC do not exist yet (Phase 6); endpoints are local-development only
until then. Nothing here trusts the frontend: all validation is server-side.
"""

from __future__ import annotations

import os

from fastapi.responses import JSONResponse

from ..database.documents import DocumentStore, default_db_path
from ..database.neo4j import Neo4jConfig, Neo4jService
from ..services.ingestion import IngestionService
from ..services.validation import IngestionError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def raw_dir() -> str:
    return os.environ.get("RAW_DATA_DIR",
                          os.path.join(REPO_ROOT, "data", "raw"))


def processed_dir() -> str:
    return os.environ.get("PROCESSED_DATA_DIR",
                          os.path.join(REPO_ROOT, "data", "processed"))


def db_path() -> str:
    return os.environ.get("DOCUMENT_DB_PATH", default_db_path())


_service: IngestionService | None = None


def get_service() -> IngestionService:
    global _service
    if _service is None:
        _service = IngestionService(DocumentStore(db_path()),
                                    raw_dir(), processed_dir())
    return _service


def reset_service() -> None:
    """Test hook: drop the cached service so env overrides take effect."""
    global _service
    _service = None


_graph_service: Neo4jService | None = None
_graph_override = None


def get_graph_service() -> Neo4jService:
    """Neo4j service from environment (password required). Fails with a
    structured error — never an import traceback — when unconfigured."""
    global _graph_service
    if _graph_override is not None:
        return _graph_override
    if _graph_service is None:
        _graph_service = Neo4jService(Neo4jConfig.from_env())
    return _graph_service


def set_graph_service_override(service) -> None:
    """Test hook: inject a fake/driver-backed service."""
    global _graph_override
    _graph_override = service


def reset_graph_service() -> None:
    global _graph_service, _graph_override
    _graph_service = None
    _graph_override = None


def error_response(exc: IngestionError) -> JSONResponse:
    """Structured error envelope. Never includes paths or tracebacks."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"success": False,
                 "error": {"code": exc.code, "message": exc.message,
                           "details": exc.details}},
    )


def ok(data: dict, message: str, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "message": message}
