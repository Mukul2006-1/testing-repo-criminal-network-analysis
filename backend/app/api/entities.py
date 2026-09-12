"""Phase 3 — POST /api/entities/extract + POST /api/entities/resolve.

Extract is read-only NLP over Phase 2 processed records (or inline text);
resolve persists canonical entities + mentions and returns the resolution
contract. Both follow the API_SPEC.md envelope; Phase 2 routes are
untouched. No graph, analytics, or auth changes in this phase.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..schemas.entities import ExtractRequest, ResolveRequest
from ..services import nlp as nlp_mod
from ..services import auth as auth_svc
from ..services.entity_resolution import resolve_document
from ..services.graph_builder import build_gazetteer as _gazetteer
from ..services.validation import IngestionError
from .deps import error_response, get_service, ok, processed_dir

router = APIRouter()

_STRUCTURED_FIELDS = {
    "CDR": (("caller", "PHONE"), ("receiver", "PHONE")),
    "TRANSACTION": (("sender_account", "ACCOUNT"),
                    ("receiver_account", "ACCOUNT")),
}
_TEXT_FIELDS = {"FIR": ("text",), "VEHICLE": ("owner_name",),
                "LOCATION": ("name",)}


def _extract_record(record: dict, names: list[str],
                    locations: list[str]) -> list[dict]:
    source_type = record.get("source_type")
    normalized = record.get("normalized") or {}
    original = record.get("original") or {}
    entities: list[dict] = []
    for field, entity_type in _STRUCTURED_FIELDS.get(source_type, ()):
        value = normalized.get(field) or original.get(field)
        if value:
            entities.append(nlp_mod.structured_entity(
                entity_type, str(value), source_field=field))
    for field in _TEXT_FIELDS.get(source_type, ()):
        text = normalized.get(field) or original.get(field)
        if text and str(text).strip():
            result = nlp_mod.extract_entities(
                str(text), record.get("source_id", "unknown"),
                known_names=names, known_locations=locations)
            entities.extend(result["entities"])
    if source_type not in _STRUCTURED_FIELDS and \
            source_type not in _TEXT_FIELDS:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             f"Extraction unsupported for {source_type}.",
                             http_status=422)
    return entities


@router.post("/entities/extract")
def extract(body: ExtractRequest,
            user: dict = Depends(auth_svc.require_user)):
    try:
        store = get_service().store
        names, locations = _gazetteer(store)
        if body.text is not None:
            result = nlp_mod.extract_entities(
                body.text, body.document_id, known_names=names,
                known_locations=locations)
        else:
            document = store.get_document(body.upload_id)
            if document is None:
                raise IngestionError(
                    "UPLOAD_NOT_FOUND",
                    f"Unknown upload_id: {body.upload_id}", http_status=404)
            if document["status"] != "PROCESSED":
                raise IngestionError(
                    "DOCUMENT_NOT_PROCESSED",
                    f"Upload {body.upload_id} has status "
                    f"{document['status']}; process it first.",
                    http_status=422)
            path = os.path.join(processed_dir(), body.upload_id,
                                "records.json")
            if not os.path.isfile(path):
                raise IngestionError("PROCESSING_FAILED",
                                     "Processed output is missing.",
                                     http_status=500)
            with open(path, encoding="utf-8") as fh:
                records = json.load(fh)
            entities: list[dict] = []
            for record in records:
                entities.extend(_extract_record(record, names, locations))
            for i, entity in enumerate(entities, 1):
                entity["id"] = f"temp_{i:03d}"
            result = {"document_id": body.upload_id, "entities": entities,
                      "relationships": []}
    except IngestionError as exc:
        return error_response(exc)
    return ok(result,
              f"Extracted {len(result['entities'])} entities "
              f"for {result['document_id']}.")


@router.post("/entities/resolve")
def resolve(body: ResolveRequest,
            user: dict = Depends(auth_svc.require_user)):
    try:
        if len(body.entities) > 500:
            raise IngestionError("TOO_MANY_ENTITIES",
                                 "At most 500 entities per request.",
                                 http_status=422)
        result = resolve_document(
            get_service().store, body.document_id,
            [entity.model_dump() for entity in body.entities],
            doc_attrs=body.doc_attrs,
            fuzzy_threshold=body.fuzzy_threshold)
    except IngestionError as exc:
        return error_response(exc)
    return ok(result,
              f"Resolved {len(result['resolved'])} entities "
              f"for {body.document_id}.")
