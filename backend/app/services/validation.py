"""Phase 2 — file and record validation (standard library only).

Uploaded files are untrusted. Every check here fails closed with a
structured error code; nothing is silently discarded and no stack traces
leave this layer (see `IngestionError`).
"""

from __future__ import annotations

import os
import re

DATASET_TYPES = ("FIR", "CDR", "TRANSACTION", "VEHICLE", "LOCATION")

ALLOWED_EXTENSIONS = {".csv", ".json", ".txt"}

# Per API_SPEC.md §1: 25 MB default, overridable for deployment.
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_RECORDS = int(os.environ.get("MAX_UPLOAD_RECORDS", "50000"))
MAX_FILENAME_LEN = 255

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Required/optional columns for CSV/JSON payloads (Phase 1 schemas).
SCHEMAS: dict[str, dict] = {
    "FIR": {
        "required": ["fir_id", "date", "text"],
        "optional": ["police_station", "source"],
        "id_field": "fir_id",
    },
    "CDR": {
        "required": ["cdr_id", "caller", "receiver", "timestamp", "duration"],
        "optional": ["source"],
        "id_field": "cdr_id",
    },
    "TRANSACTION": {
        "required": ["transaction_id", "sender_account", "receiver_account",
                     "amount", "currency", "timestamp"],
        "optional": ["source"],
        "id_field": "transaction_id",
    },
    "VEHICLE": {
        "required": ["vehicle_id", "registration_number", "owner_name"],
        "optional": ["source"],
        "id_field": "vehicle_id",
    },
    "LOCATION": {
        "required": ["location_id", "name"],
        "optional": ["latitude", "longitude", "source"],
        "id_field": "location_id",
    },
}

# TXT carries free narrative text only; Phase 3 (NLP) will parse it.
# Only FIR accepts TXT because only FIR has a free-text schema.
TXT_DATASET_TYPES = ("FIR",)
TXT_REQUIRED = ["text"]


class IngestionError(Exception):
    """Structured pipeline failure. `details` is JSON-safe, never a trace."""

    def __init__(self, code: str, message: str,
                 details: list | dict | None = None,
                 http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []
        self.http_status = http_status


def validate_filename(filename: str | None) -> str:
    """Return the display-safe filename or raise INVALID_FILE_NAME.

    The returned value is for display/provenance only — storage paths are
    generated server-side and never derived from this value.
    """
    if not filename or not filename.strip():
        raise IngestionError("INVALID_FILE_NAME",
                             "Filename is missing.", http_status=400)
    name = filename.strip()
    if (len(name) > MAX_FILENAME_LEN or "/" in name or "\\" in name
            or "\x00" in name or name in (".", "..")
            or name.startswith("..") or os.path.isabs(name)):
        raise IngestionError("INVALID_FILE_NAME",
                             f"Unsafe filename rejected: {name[:64]}",
                             http_status=400)
    return name


def extension_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def validate_file_meta(filename: str, size_bytes: int,
                       dataset_type: str) -> str:
    """Validate type/size/extension. Returns the lowercase extension."""
    if dataset_type not in DATASET_TYPES:
        raise IngestionError(
            "INVALID_RECORD_STRUCTURE",
            f"dataset_type must be one of {list(DATASET_TYPES)}.",
            details=[{"field": "dataset_type", "issue": "invalid value"}],
            http_status=422)
    ext = extension_of(filename)
    if ext == ".pdf":
        raise IngestionError(
            "PDF_EXTRACTION_NOT_SUPPORTED",
            "PDF uploads are accepted as a future extension point only; "
            "text extraction is not implemented in Phase 2.",
            http_status=422)
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestionError(
            "UNSUPPORTED_FILE_TYPE",
            f"Extension '{ext or '(none)'}' is not supported. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}.",
            http_status=422)
    if size_bytes <= 0:
        raise IngestionError("INVALID_CSV", "Uploaded file is empty.",
                             http_status=422)
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise IngestionError(
            "FILE_TOO_LARGE",
            f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit.",
            http_status=413)
    return ext


def expected_schema(dataset_type: str, extension: str) -> dict:
    """Column contract for a (type, format) pair. TXT has its own rule."""
    if extension == ".txt":
        if dataset_type not in TXT_DATASET_TYPES:
            raise IngestionError(
                "INVALID_RECORD_STRUCTURE",
                f"TXT uploads are only supported for dataset types "
                f"{list(TXT_DATASET_TYPES)}.",
                details=[{"field": "dataset_type", "issue": "TXT not applicable"}],
                http_status=422)
        return {"required": list(TXT_REQUIRED), "optional": [],
                "id_field": None}
    return SCHEMAS[dataset_type]


def validate_record(dataset_type: str, record: object, index: int,
                    extension: str) -> list[dict]:
    """Structural check of one parsed record. Returns a list of field errors.

    Semantic checks (timestamps, numerics, phones) run in normalization and
    are reported with their own codes; this layer only enforces presence and
    ID shape so that every rejection is attributable to a field.
    """
    errors: list[dict] = []
    if not isinstance(record, dict):
        return [{"record": index, "field": "(record)",
                 "issue": "record must be an object",
                 "code": "INVALID_RECORD_STRUCTURE"}]
    schema = expected_schema(dataset_type, extension)
    for field in schema["required"]:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({"record": index, "field": field,
                           "issue": "missing required field",
                           "code": "MISSING_REQUIRED_FIELD"})
    id_field = schema["id_field"]
    if id_field and record.get(id_field) not in (None, ""):
        rid = str(record[id_field])
        if not ID_RE.match(rid):
            errors.append({"record": index, "field": id_field,
                           "issue": "invalid id format",
                           "code": "INVALID_RECORD_STRUCTURE"})
    return errors
