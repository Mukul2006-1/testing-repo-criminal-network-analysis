"""Phase 3 — deterministic entity resolution (standard library only).

Explainable method chain per decision, strongest evidence first:

1. ``exact_match`` — same type + identical normalized value (confidence 1.0).
2. ``phone_match`` / ``vehicle_match`` / ``account_match`` — same type +
   identical normalized strong identifier (confidence 0.97).
3. ``name_similarity`` (+ ``shared_attribute`` / ``phone_match`` /
   ``account_match`` / ``vehicle_match``) — fuzzy name similarity at or
   above threshold AND at least one shared strong attribute from the same
   source document. The similarity gate is deliberately permissive
   (default 0.65: "R. Sharma"~"Rahul Sharma" score 0.76) because the
   shared-attribute requirement carries the safety — similar names without
   shared evidence always create a new canonical entity.
4. ``new_entity`` — no reliable match; a fresh canonical ID is assigned.

No LLM is involved; every decision lists its method(s) and every mention
(row) keeps verbatim text, confidence, method and document provenance.
Client-supplied temp IDs are echoed for traceability but never trusted as
canonical IDs — the store assigns those.
"""

from __future__ import annotations

import difflib
import uuid

from .normalization import normalized_name_key
from .validation import IngestionError

ENTITY_TYPES = ("PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION",
                "DATE", "ACCOUNT")

STRONG_METHOD = {"PHONE": "phone_match", "VEHICLE": "vehicle_match",
                 "ACCOUNT": "account_match"}
FUZZY_TYPES = ("PERSON", "ORGANIZATION", "LOCATION")
PREFIX = {"PERSON": "person_", "PHONE": "phone_", "LOCATION": "location_",
          "VEHICLE": "vehicle_", "ORGANIZATION": "org_", "DATE": "date_",
          "ACCOUNT": "account_"}
ATTR_KEYS = ("phones", "accounts", "vehicles", "organizations")


def _check_extraction(entity_type: str, value: object, confidence: object,
                      document_id: str) -> tuple[str, float]:
    if entity_type not in ENTITY_TYPES:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             f"Unknown entity type: {entity_type!r}",
                             http_status=422)
    text = str(value).strip() if value is not None else ""
    if not text or len(text) > 1000:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "Entity value must be 1-1000 characters.",
                             http_status=422)
    try:
        conf = float(confidence)
    except (TypeError, ValueError) as exc:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "Entity confidence must be numeric.",
                             http_status=422) from exc
    if not 0.0 <= conf <= 1.0:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "Entity confidence must be in [0, 1].",
                             http_status=422)
    if not document_id or len(str(document_id)) > 64:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "document_id is required (max 64 chars).",
                             http_status=422)
    return text, conf


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _shared_evidence(doc_attrs: dict, entity_attrs: dict) -> list[str]:
    """Strong-attribute overlap between the incoming mention's document and a
    candidate entity. Returns method names (e.g. ["phone_match"])."""
    methods = []
    for key, method in (("phones", "phone_match"),
                        ("accounts", "account_match"),
                        ("vehicles", "vehicle_match")):
        doc_vals = {str(v) for v in (doc_attrs or {}).get(key, []) if v}
        ent_vals = {str(v) for v in (entity_attrs or {}).get(key, []) if v}
        if doc_vals & ent_vals:
            methods.append(method)
    doc_orgs = {normalized_name_key(str(v))
                for v in (doc_attrs or {}).get("organizations", []) if v}
    ent_orgs = {normalized_name_key(str(v))
                for v in (entity_attrs or {}).get("organizations", []) if v}
    if doc_orgs & ent_orgs:
        methods.append("shared_attribute")
    return methods


def _merge_attrs(entity_attrs: dict, doc_attrs: dict) -> dict:
    merged = {k: list((entity_attrs or {}).get(k, [])) for k in ATTR_KEYS}
    for key in ATTR_KEYS:
        seen = set(merged[key])
        for value in (doc_attrs or {}).get(key, []):
            if value and value not in seen:
                seen.add(value)
                merged[key].append(value)
    return merged


def resolve_one(store, entity_type: str, value: str, normalized_value: str,
                confidence: float, method: str, document_id: str,
                doc_attrs: dict | None = None,
                fuzzy_threshold: float = 0.65) -> dict:
    """Resolve one extracted mention. Returns the resolution contract::

        {"canonical_id": ..., "matches": [{"value", "confidence"}],
         "resolution_method": [...]}
    """
    text, conf = _check_extraction(entity_type, value, confidence,
                                   document_id)
    normalized = (normalized_value or "").strip()
    if not normalized:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "normalized_value is required.",
                             http_status=422)
    if not 0.0 <= fuzzy_threshold <= 1.0:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "fuzzy_threshold must be in [0, 1].",
                             http_status=422)
    doc_attrs = doc_attrs or {}

    decision = _match(store, entity_type, normalized, doc_attrs,
                      fuzzy_threshold)
    if decision is None:
        canonical_id = f"{PREFIX[entity_type]}{store.next_counter(PREFIX[entity_type]):03d}"
        store.create_entity({
            "id": canonical_id, "type": entity_type,
            "canonical_name": text[:256], "normalized_name": normalized[:256],
            "attributes": {k: list(doc_attrs.get(k, [])) for k in ATTR_KEYS},
        })
        methods = ["new_entity"]
    else:
        canonical_id, methods, merge_conf = decision
        entity = store.get_entity(canonical_id)
        store.update_entity_attrs(
            canonical_id, _merge_attrs(entity.get("attributes"), doc_attrs))

    store.create_mention({
        "id": f"men_{uuid.uuid4().hex[:8]}", "entity_id": canonical_id,
        "document_id": str(document_id), "text": text[:1000],
        "confidence": conf, "extraction_method": (method or "unknown")[:64],
    })
    matches = [{"value": m["text"], "confidence": m["confidence"]}
               for m in store.list_mentions(canonical_id, limit=10)]
    return {"canonical_id": canonical_id, "matches": matches,
            "resolution_method": methods}


def _match(store, entity_type: str, normalized: str, doc_attrs: dict,
           fuzzy_threshold: float) -> tuple[str, list[str], float] | None:
    """Return (canonical_id, methods, confidence) or None for new entity."""
    existing = store.find_entities_by_normalized(entity_type, normalized)
    if existing:
        if entity_type in STRONG_METHOD:
            return existing[0]["id"], [STRONG_METHOD[entity_type]], 0.97
        return existing[0]["id"], ["exact_match"], 1.0

    if entity_type in FUZZY_TYPES:
        best = None
        for cand in store.list_entities_by_type(entity_type):
            sim = _similarity(normalized, cand["normalized_name"])
            if sim < fuzzy_threshold:
                continue
            evidence = _shared_evidence(doc_attrs, cand.get("attributes"))
            if not evidence:
                continue  # similar name alone is never enough
            score = sim if best is None else best[0]
            if best is None or sim > score:
                best = (sim, cand["id"], ["name_similarity"] + evidence)
        if best is not None:
            sim, cid, methods = best
            return cid, methods, round(min(0.95, 0.75 + 0.20 * sim), 2)
    return None


def resolve_document(store, document_id: str, extractions: list[dict],
                     doc_attrs: dict | None = None,
                     fuzzy_threshold: float = 0.65) -> dict:
    """Resolve every extraction from one document, in order, so later
    mentions see entities created by earlier ones."""
    if not isinstance(extractions, list):
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "extractions must be a list.", http_status=422)
    doc_attrs = dict(doc_attrs or {})
    if not any(doc_attrs.get(k) for k in ATTR_KEYS):
        # Derive shared-evidence attributes from the document's own
        # strong-identifier extractions (same-document co-occurrence).
        derived = {k: [] for k in ATTR_KEYS}
        mapping = {"PHONE": "phones", "ACCOUNT": "accounts",
                   "VEHICLE": "vehicles", "ORGANIZATION": "organizations"}
        for ext in extractions:
            key = mapping.get(ext.get("type"))
            if key and ext.get("normalized_value"):
                derived[key].append(ext["normalized_value"])
        doc_attrs = {**derived, **{k: v for k, v in doc_attrs.items() if v}}

    resolved = []
    for ext in extractions:
        result = resolve_one(
            store, ext.get("type"), ext.get("value", ""),
            ext.get("normalized_value", ""), ext.get("confidence", 0.0),
            ext.get("method", "unknown"), document_id, doc_attrs,
            fuzzy_threshold)
        resolved.append({"temp_id": ext.get("id"), "type": ext.get("type"),
                         **result})
    return {"document_id": document_id, "resolved": resolved}
