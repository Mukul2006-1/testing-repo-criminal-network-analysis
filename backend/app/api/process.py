"""Phase 2 — POST /api/process + GET /api/process/{job_id}.

Ingestion/preprocessing scope only: VALIDATION -> PARSING -> NORMALIZATION.
NLP, resolution, graph and analytics stages do not exist yet and are never
claimed. Processing runs synchronously; the returned status (SUCCEEDED /
PARTIAL / FAILED) reflects verified writes, never intent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..schemas.process import ProcessRequest
from ..services import auth as auth_svc
from ..services import audit as audit_mod
from ..services.validation import ID_RE, IngestionError
from .deps import error_response, get_service, ok

router = APIRouter()


@router.post("/process")
def process_document(body: ProcessRequest,
                     user: dict = Depends(auth_svc.require_user)):
    try:
        result = get_service().process(body.upload_id)
        audit_mod.record(get_service().store,
                         actor=user.get("email", user["id"]),
                         action="ingest.process", target=body.upload_id,
                         output_hash=audit_mod.digest(result["status"]))
    except IngestionError as exc:
        return error_response(exc)
    message = {"SUCCEEDED": "Processing completed; output stored.",
               "PARTIAL": "Processing completed with invalid records; "
                          "see errors.",
               "FAILED": "Processing failed; no records stored."}[result["status"]]
    return ok(result, message)


@router.get("/process/{job_id}")
def get_job(job_id: str, user: dict = Depends(auth_svc.require_user)):
    if not ID_RE.match(job_id):
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": {"code": "INVALID_ID",
                               "message": "Malformed job id.",
                               "details": []}},
        )
    job = get_service().store.get_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"success": False,
                     "error": {"code": "JOB_NOT_FOUND",
                               "message": f"Unknown job_id: {job_id}",
                               "details": []}},
        )
    return ok({"job_id": job["id"], "upload_id": job["upload_id"],
               "status": job["status"], "result": job["result"]},
              "Job retrieved.")
