"""Phase 2 — ingestion orchestrator (standard library only).

Pipeline: file bytes -> meta validation -> raw storage -> parse ->
structural validation -> normalization -> processed output.

STANDARDIZED RECORD CONTRACT (Phase 2 output -> Phase 3 input)
--------------------------------------------------------------
Phase 3 (NLP/NER + entity resolution) must never parse raw file formats.
It consumes only these records::

    {
      "source_id": "CDR_001",          # record ID, or "<upload_id>#L<n>" for TXT lines
      "source_type": "CDR",            # FIR | CDR | TRANSACTION | VEHICLE | LOCATION
      "upload_id": "upl_9f3a...",
      "original": {...},               # verbatim parsed record (provenance)
      "normalized": {...},             # canonical forms + match keys, None only
                                       # for absent optional fields
      "provenance": {
        "source_file": "cdr_batch.csv",# original client filename (display only)
        "dataset_type": "CDR",
        "ingested_at": "2026-...Z",
        "status": "PROCESSED",
      },
    }

Rules for consumers: `original` is evidence (never mutate); `normalized`
holds derived values; absent optionals are explicit None; every record is
traceable to its upload via `upload_id` + `source_id`.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from .normalization import normalize_record, normalize_whitespace
from .parser import parse
from .validation import (
    IngestionError,
    expected_schema,
    validate_file_meta,
    validate_filename,
    validate_record,
)

STAGES = ["VALIDATION", "PARSING", "NORMALIZATION"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_upload_id() -> str:
    return f"upl_{uuid.uuid4().hex[:8]}"


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:8].upper()}"


def storage_name(extension: str) -> str:
    """Server-generated storage name. Never derived from user input."""
    return f"{uuid.uuid4().hex}{extension}"


def source_id_for(dataset_type: str, id_field: str | None, record: dict,
                  upload_id: str, index: int) -> str:
    if id_field and record.get(id_field) not in (None, ""):
        return str(record[id_field]).strip()
    return f"{upload_id}#L{index + 1}"


def standardize(dataset_type: str, upload_id: str, source_file: str,
                records: list[dict], extension: str) -> tuple[list[dict], list[dict]]:
    """Validate + normalize parsed records.

    Returns (standardized, errors). Invalid records are reported explicitly
    in `errors` — never silently discarded — and excluded from output.
    """
    schema = expected_schema(dataset_type, extension)
    id_field = schema["id_field"]
    standardized: list[dict] = []
    errors: list[dict] = []
    for index, record in enumerate(records):
        structural = validate_record(dataset_type, record, index, extension)
        if structural:
            errors.extend(structural)
            continue
        if extension == ".txt":
            # Narrative lines carry no record IDs/dates; Phase 3 (NLP) parses
            # them. Only whitespace normalization applies here.
            normalized, semantic = (
                {"text": normalize_whitespace(str(record.get("text", "")))}, [])
        else:
            normalized, semantic = normalize_record(dataset_type, record, index)
        if semantic:
            errors.extend(semantic)
            continue
        standardized.append({
            "source_id": source_id_for(dataset_type, id_field, record,
                                       upload_id, index),
            "source_type": dataset_type,
            "upload_id": upload_id,
            "original": dict(record),
            "normalized": normalized,
            "provenance": {
                "source_file": source_file,
                "dataset_type": dataset_type,
                "ingested_at": now_iso(),
                "status": "PROCESSED",
            },
        })
    return standardized, errors


class IngestionService:
    """Coordinates upload storage and processing against a document store.

    The store only needs: create_document / get_document / update_status /
    find_by_hash / create_job / update_job / get_job (see
    `database.documents.DocumentStore`, which mirrors DATABASE_SCHEMA.md).
    Raw bytes live under raw_dir/<TYPE>/, processed JSON under
    processed_dir/<upload_id>/records.json. Raw files are never modified.
    """

    def __init__(self, store, raw_dir: str, processed_dir: str) -> None:
        self.store = store
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir

    # -- upload ---------------------------------------------------------
    def upload(self, content: bytes, filename: str, dataset_type: str,
               source_name: str | None = None,
               description: str | None = None,
               uploaded_by: str = "system") -> dict:
        display_name = validate_filename(filename)
        if source_name is not None and len(source_name) > 128:
            raise IngestionError("INVALID_RECORD_STRUCTURE",
                                 "source_name exceeds 128 characters.",
                                 http_status=422)
        if description is not None and len(description) > 1000:
            raise IngestionError("INVALID_RECORD_STRUCTURE",
                                 "description exceeds 1000 characters.",
                                 http_status=422)
        ext = validate_file_meta(display_name, len(content), dataset_type)

        file_hash = hashlib.sha256(content).hexdigest()
        existing = self.store.find_by_hash(file_hash)
        if existing is not None:
            raise IngestionError(
                "DUPLICATE_UPLOAD",
                "Identical file already ingested; no new document created.",
                details=[{"upload_id": existing["id"]}],
                http_status=409)

        upload_id = new_upload_id()
        raw_path = os.path.join(self.raw_dir, dataset_type,
                                storage_name(ext))
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        with open(raw_path, "wb") as fh:
            fh.write(content)

        try:
            record_count = len(parse(content, ext))
        except IngestionError:
            record_count = 0  # stored honestly as UPLOADED; /process reports it
        document = {
            "id": upload_id, "type": dataset_type, "filename": display_name,
            "source": (source_name or "").strip() or None,
            "uploaded_by": uploaded_by or "system",  # authenticated user id
            "uploaded_at": now_iso(), "status": "UPLOADED",
            "file_hash": file_hash,
            "metadata": {"size_bytes": len(content), "record_count": record_count,
                         "extension": ext,
                         "storage": os.path.basename(raw_path),
                         "description": (description or "").strip() or None},
        }
        try:
            self.store.create_document(document)
        except Exception:
            try:
                os.remove(raw_path)
            except OSError:
                pass
            raise
        return document

    # -- process ----------------------------------------------------------
    def process(self, upload_id: str) -> dict:
        document = self.store.get_document(upload_id)
        if document is None:
            raise IngestionError("UPLOAD_NOT_FOUND",
                                 f"Unknown upload_id: {upload_id}",
                                 http_status=404)
        if document["status"] == "PROCESSING":
            raise IngestionError("ALREADY_PROCESSING",
                                 f"{upload_id} is already processing.",
                                 http_status=409)
        job_id = new_job_id()
        self.store.update_status(upload_id, "VALIDATING")
        self.store.create_job({"id": job_id, "upload_id": upload_id,
                               "status": "RUNNING", "stages": STAGES,
                               "created_at": now_iso()})
        try:
            raw_path = self._raw_path_for(document)
            with open(raw_path, "rb") as fh:
                content = fh.read()
            ext = (document.get("metadata") or {}).get("extension") or \
                os.path.splitext(document["filename"])[1].lower()
            self.store.update_status(upload_id, "PROCESSING")
            records = parse(content, ext)
            standardized, errors = standardize(
                document["type"], upload_id, document["filename"],
                records, ext)
            out_dir = os.path.join(self.processed_dir, upload_id)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, "records.json")
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(standardized, fh, indent=2)

            if not standardized:
                final_doc, final_job = "FAILED", "FAILED"
            elif errors:
                final_doc, final_job = "PROCESSED", "PARTIAL"
            else:
                final_doc, final_job = "PROCESSED", "SUCCEEDED"
            self.store.update_status(
                upload_id, final_doc,
                {"valid_count": len(standardized),
                 "invalid_count": len(errors),
                 "errors": errors[:50],
                 "truncated_errors": max(0, len(errors) - 50)})
            result = {"job_id": job_id, "upload_id": upload_id,
                      "status": final_job, "stages": STAGES,
                      "valid_count": len(standardized),
                      "invalid_count": len(errors),
                      "errors": errors[:50],
                      "created_at": now_iso()}
            self.store.update_job(job_id, final_job, result)
            return result
        except IngestionError as exc:
            self.store.update_status(upload_id, "FAILED",
                                     {"error": {"code": exc.code,
                                                "message": exc.message}})
            result = {"job_id": job_id, "upload_id": upload_id,
                      "status": "FAILED", "stages": STAGES,
                      "valid_count": 0, "invalid_count": 0,
                      "errors": [{"code": exc.code, "message": exc.message}],
                      "created_at": now_iso()}
            self.store.update_job(job_id, "FAILED", result)
            return result

    def _raw_path_for(self, document: dict) -> str:
        rel = (document.get("metadata") or {}).get("storage")
        if not rel:
            raise IngestionError("PROCESSING_FAILED",
                                 "Stored file reference missing; cannot process.",
                                 http_status=500)
        # Defense in depth: storage refs are server-generated "<hex>.<ext>";
        # reject anything else before touching the filesystem.
        name = os.path.basename(rel)
        if name != rel or not name.replace(".", "").replace("_", "").isalnum():
            raise IngestionError("PROCESSING_FAILED",
                                 "Stored file reference invalid.",
                                 http_status=500)
        path = os.path.join(self.raw_dir, document["type"], name)
        if not os.path.isfile(path):
            raise IngestionError("PROCESSING_FAILED",
                                 "Stored source file is missing.",
                                 http_status=500)
        return path
