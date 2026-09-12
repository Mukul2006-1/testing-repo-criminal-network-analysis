"""Crime Network Intelligence System — FastAPI entrypoint.

Phase 6: full application API — ingestion, NLP/resolution, knowledge
graph, analytics/anomaly/priority, timeline, search, investigation, and
JWT authentication with server-side RBAC. React dashboard is served
separately (see frontend/). No external AI/data APIs
(see PROJECT_SPEC.md phases).
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.analytics import router as analytics_router
from .api.auth import router as auth_router
from .api.deps import error_response
from .api.entities import router as entities_router
from .api.graph import router as graph_router
from .api.process import router as process_router
from .api.search import router as search_router
from .api.timeline import router as timeline_router
from .api.uploads import router as upload_router
from .services.validation import IngestionError

app = FastAPI(title="Crime Network Intelligence System", version="0.7.0")

# CORS: explicit frontend origin allowlist only — never "*" with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in
                   os.environ.get("FRONTEND_URL",
                                  "http://localhost:5173").split(",")
                   if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.include_router(upload_router, prefix="/api")
app.include_router(process_router, prefix="/api")
app.include_router(entities_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")


@app.exception_handler(IngestionError)
async def ingestion_error_handler(request, exc: IngestionError):
    """Structured envelope for IngestionError raised anywhere — including
    auth dependencies — so no failure ever leaks a traceback or 500."""
    return error_response(exc)


@app.get("/health")
def health() -> dict:
    """Liveness probe. Unauthenticated by design (see API_SPEC.md)."""
    return {"success": True, "data": {"status": "ok"}, "message": "Backend is running."}
