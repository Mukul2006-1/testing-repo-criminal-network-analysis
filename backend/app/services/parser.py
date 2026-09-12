"""Phase 2 — safe parsers for CSV / JSON / TXT (standard library only).

Parsing never executes content. PDF is an explicit extension point: it is
detected and rejected with a structured code until extraction lands.
"""

from __future__ import annotations

import csv
import io
import json

from .validation import IngestionError, MAX_RECORDS


def decode_bytes(content: bytes) -> str:
    """Decode upload bytes. Only UTF-8 is accepted; anything else is an
    explicit error (unexpected encodings must not be guessed silently)."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError("INVALID_ENCODING",
                             "File must be UTF-8 encoded.",
                             http_status=422) from exc


def parse_csv(text: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(text))
    except csv.Error as exc:
        raise IngestionError("INVALID_CSV",
                             f"CSV header could not be parsed: {exc}",
                             http_status=422) from exc
    if not reader.fieldnames:
        raise IngestionError("INVALID_CSV", "CSV has no header row.",
                             http_status=422)
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise IngestionError("INVALID_CSV",
                             f"Malformed CSV body: {exc}",
                             http_status=422) from exc
    if not rows:
        raise IngestionError("INVALID_CSV", "CSV contains no data rows.",
                             http_status=422)
    return rows


def parse_json(text: str) -> list[dict]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestionError("INVALID_JSON",
                             f"Malformed JSON: {exc.msg} (line {exc.lineno}).",
                             http_status=422) from exc
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload = payload["records"]
    if not isinstance(payload, list) or not payload:
        raise IngestionError(
            "INVALID_JSON",
            "JSON must be a non-empty array of objects (or "
            '{"records": [...]}).',
            http_status=422)
    return payload


def parse_txt(text: str) -> list[dict]:
    """One record per non-empty line: {"text": line} (narrative for Phase 3)."""
    rows = [{"text": line} for line in text.splitlines() if line.strip()]
    if not rows:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "TXT file contains no text lines.",
                             http_status=422)
    return rows


def parse(content: bytes, extension: str) -> list[dict]:
    """Parse upload bytes by extension. Enforces the record-count cap."""
    if extension == ".pdf":
        raise IngestionError(
            "PDF_EXTRACTION_NOT_SUPPORTED",
            "PDF text extraction is a future extension point; "
            "not implemented in Phase 2.",
            http_status=422)
    text = decode_bytes(content)
    if extension == ".csv":
        records = parse_csv(text)
    elif extension == ".json":
        records = parse_json(text)
    elif extension == ".txt":
        records = parse_txt(text)
    else:  # guarded earlier by validate_file_meta; fail closed anyway
        raise IngestionError("UNSUPPORTED_FILE_TYPE",
                             f"Extension '{extension}' is not supported.",
                             http_status=422)
    if len(records) > MAX_RECORDS:
        raise IngestionError(
            "TOO_MANY_RECORDS",
            f"File has {len(records)} records; limit is {MAX_RECORDS}.",
            http_status=413)
    return records
