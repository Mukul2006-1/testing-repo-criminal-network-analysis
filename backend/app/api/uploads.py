"""Phase 2 — POST /api/upload (API_SPEC.md §1, ingestion scope only).

Stores the source file immutably and creates document metadata with status
UPLOADED. It does NOT parse/validate records — that is POST /api/process.
A 201 here means "stored", never "fully processed".

Requires authentication (any role); uploads are attributed to the caller.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..services import auth as auth_svc
from ..services.validation import (
    MAX_FILE_SIZE_BYTES,
    IngestionError,
)
from .deps import error_response, get_service, ok

router = APIRouter()

_CHUNK = 1024 * 1024


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile | None = None,
    dataset_type: str = Form(...),
    source_name: str | None = Form(None),
    description: str | None = Form(None),
    user: dict = Depends(auth_svc.require_user),
):
    if file is None or not file.filename:
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": {"code": "MISSING_FILE",
                               "message": "Multipart field 'file' is required.",
                               "details": []}},
        )
    try:
        # Stream with a hard cap: never buffer an unbounded upload.
        chunks: list[bytes] = []
        total = 0
        while True:
            piece = await file.read(_CHUNK)
            if not piece:
                break
            total += len(piece)
            if total > MAX_FILE_SIZE_BYTES:
                raise IngestionError(
                    "FILE_TOO_LARGE",
                    "File exceeds the size limit.", http_status=413)
            chunks.append(piece)
        content = b"".join(chunks)
        document = get_service().upload(
            content, file.filename, dataset_type.strip().upper(),
            source_name=source_name, description=description,
            uploaded_by=user["id"])
    except IngestionError as exc:
        return error_response(exc)
    meta = document["metadata"]
    return ok(
        {"upload_id": document["id"], "dataset_type": document["type"],
         "filename": document["filename"],
         "size_bytes": meta.get("size_bytes"),
         "record_count": meta.get("record_count"),
         "status": document["status"], "source_id": document["id"],
         "uploaded_at": document["uploaded_at"],
         "uploaded_by": document["uploaded_by"]},
        "File uploaded and stored. Run POST /api/process to validate it.",
        status_code=201,
    )
