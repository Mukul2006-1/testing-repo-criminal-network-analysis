"""Phase 3 — NLP entity extraction (spaCy NER + deterministic rules).

Hybrid design, honest about model limits: spaCy's pretrained NER covers
PERSON / ORGANIZATION / LOCATION / DATE, while PHONE, VEHICLE and ACCOUNT
identifiers — which the model does not recognize — are extracted with
bounded deterministic regex rules plus an optional caller-supplied
gazetteer (e.g. known alias spellings). Nothing is ever invented: every
emitted entity corresponds to a span actually present in the input text.

Security posture: input text is untrusted DATA (never executed, never
logged — only counts/ids leave this module); regexes are linear-time
(no nested quantifiers); entity values are length-capped; Unicode is
handled as plain Python str with an overall length cap.
"""

from __future__ import annotations

import os
import re

from .normalization import (
    normalize_account,
    normalize_date,
    normalize_phone,
    normalize_vehicle,
    normalized_name_key,
)
from .validation import IngestionError

ENTITY_TYPES = ("PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION",
                "DATE", "ACCOUNT")

MAX_TEXT_CHARS = 200_000
MAX_ENTITY_CHARS = 256

# Priority for overlapping spans: structured > regex > gazetteer > NER.
_PRIO_STRUCTURED, _PRIO_REGEX, _PRIO_GAZETTEER, _PRIO_NER = 0, 1, 2, 3

_CONF = {
    "regex_phone": 0.97, "regex_vehicle": 0.97, "regex_account": 0.97,
    "regex_date": 0.90, "gazetteer_person": 0.87,
    "gazetteer_location": 0.85, "ner_person": 0.90, "ner_org": 0.85,
    "ner_gpe": 0.85, "ner_fac": 0.70, "ner_date": 0.80,
    "structured": 1.0,
}

# Linear-time patterns (bounded repetitions, no nesting).
_PHONE_PATTERNS = (
    re.compile(r"\+91[\s\-]?\(?\d{5}\)?[\s\-]?\d{5}"),
    re.compile(r"(?<![\d+])(?:91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)"),
)
_VEHICLE_PATTERN = re.compile(
    r"\b[A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}\b",
    re.IGNORECASE)
_ACCOUNT_PATTERN = re.compile(r"\bACC[\s\-]?\d{3,6}\b", re.IGNORECASE)
_DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z)?)?\b")

# Role words NER glues onto person spans ("Complainant Rahul Sharma").
_ROLE_PREFIX = re.compile(
    r"^(?:complainant|accused|victim|witness|informant|suspect)s?\b\s+",
    re.IGNORECASE)

_NER_MAP = {  # spaCy label -> (entity type, confidence key)
    "PERSON": ("PERSON", "ner_person"),
    "ORG": ("ORGANIZATION", "ner_org"),
    "GPE": ("LOCATION", "ner_gpe"),
    "LOC": ("LOCATION", "ner_gpe"),
    "FAC": ("LOCATION", "ner_fac"),
    "DATE": ("DATE", "ner_date"),
    "TIME": ("DATE", "ner_date"),
}

_nlp = None


def get_nlp():
    """Lazy singleton. Falls back to regex+gazetteer-only extraction when the
    pretrained model is unavailable (documented degradation, never silent —
    see the `nlp_backend` field on extraction output)."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(os.environ.get("SPACY_MODEL", "en_core_web_sm"))
        except Exception:
            _nlp = None
    return _nlp


def _clean_person(raw: str) -> str | None:
    name = _ROLE_PREFIX.sub("", raw.strip()).strip(" ,.")
    if len(name) < 2 or len(name) > MAX_ENTITY_CHARS:
        return None
    return name or None


def _normalize_for(entity_type: str, value: str) -> str:
    try:
        if entity_type == "PHONE":
            return normalize_phone(value)
        if entity_type == "VEHICLE":
            return normalize_vehicle(value)
        if entity_type == "ACCOUNT":
            return normalize_account(value)
        if entity_type == "DATE":
            try:
                return normalize_date(value)
            except ValueError:
                return value.strip()
        return normalized_name_key(value)
    except ValueError:
        return value.strip()


def _spans_overlap(a_start: int, a_end: int, taken: list) -> bool:
    return any(a_start < end and start < a_end for start, end in taken)


def _collect_regex(text: str, out: list) -> None:
    for pattern in _PHONE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = normalize_phone(match.group(0))
            except ValueError:
                continue
            out.append({"start": match.start(), "end": match.end(),
                        "type": "PHONE", "value": value,
                        "raw_text": match.group(0),
                        "confidence": _CONF["regex_phone"],
                        "method": "regex_phone", "prio": _PRIO_REGEX})
    for match in _VEHICLE_PATTERN.finditer(text):
        try:
            value = normalize_vehicle(match.group(0))
        except ValueError:
            continue
        out.append({"start": match.start(), "end": match.end(),
                    "type": "VEHICLE", "value": value,
                    "raw_text": match.group(0),
                    "confidence": _CONF["regex_vehicle"],
                    "method": "regex_vehicle", "prio": _PRIO_REGEX})
    for match in _ACCOUNT_PATTERN.finditer(text):
        try:
            value = normalize_account(match.group(0))
        except ValueError:
            continue
        out.append({"start": match.start(), "end": match.end(),
                    "type": "ACCOUNT", "value": value,
                    "raw_text": match.group(0),
                    "confidence": _CONF["regex_account"],
                    "method": "regex_account", "prio": _PRIO_REGEX})
    for match in _DATE_PATTERN.finditer(text):
        try:
            value = normalize_date(match.group(0))
        except ValueError:
            continue
        out.append({"start": match.start(), "end": match.end(),
                    "type": "DATE", "value": value,
                    "raw_text": match.group(0),
                    "confidence": _CONF["regex_date"],
                    "method": "regex_date", "prio": _PRIO_REGEX})


def _collect_gazetteer(text: str, names: list[str], entity_type: str,
                       conf_key: str, out: list) -> None:
    for name in names or []:
        if not name or len(name) > MAX_ENTITY_CHARS:
            continue
        pattern = re.compile(r"(?<!\w)" + r"\s+".join(
            re.escape(part) for part in name.split()) + r"(?!\w)",
            re.IGNORECASE)
        for match in pattern.finditer(text):
            raw = match.group(0)
            value = _clean_person(raw) if entity_type == "PERSON" else raw.strip()
            if not value:
                continue
            out.append({"start": match.start(), "end": match.end(),
                        "type": entity_type, "value": value, "raw_text": raw,
                        "confidence": _CONF[conf_key],
                        "method": "gazetteer", "prio": _PRIO_GAZETTEER})


def _collect_ner(text: str, nlp, out: list) -> None:
    for ent in nlp(text).ents:
        mapping = _NER_MAP.get(ent.label_)
        if mapping is None:
            continue
        entity_type, conf_key = mapping
        raw = ent.text.strip()
        if len(raw) > MAX_ENTITY_CHARS:
            continue
        value = _clean_person(raw) if entity_type == "PERSON" else raw
        if not value:
            continue
        out.append({"start": ent.start_char, "end": ent.end_char,
                    "type": entity_type, "value": value, "raw_text": raw,
                    "confidence": _CONF[conf_key],
                    "method": f"spacy_ner:{ent.label_.lower()}",
                    "prio": _PRIO_NER})


def extract_entities(text: object, document_id: str,
                     known_names: list[str] | None = None,
                     known_locations: list[str] | None = None) -> dict:
    """Extract entities from one text. Output follows the Phase 3 contract::

        {"document_id": ..., "entities": [{"id", "type", "value",
         "confidence", ...}], "relationships": []}

    `relationships` is reserved for Phase 4 (always empty here). Optional
    extras per entity (`normalized_value`, `raw_text`, `method`,
    `nlp_backend`) preserve provenance without changing the contract shape.
    """
    if not isinstance(text, str):
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "Extraction input must be text.",
                             http_status=422)
    if not document_id or not str(document_id).strip():
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             "document_id is required for extraction.",
                             http_status=422)
    if not text.strip():
        return {"document_id": document_id, "entities": [],
                "relationships": []}

    nlp = get_nlp()
    candidates: list[dict] = []
    _collect_regex(text[:MAX_TEXT_CHARS], candidates)
    _collect_gazetteer(text[:MAX_TEXT_CHARS], known_names or [], "PERSON",
                       "gazetteer_person", candidates)
    _collect_gazetteer(text[:MAX_TEXT_CHARS], known_locations or [],
                       "LOCATION", "gazetteer_location", candidates)
    if nlp is not None:
        _collect_ner(text[:MAX_TEXT_CHARS], nlp, candidates)

    candidates.sort(key=lambda c: (c["prio"], -(c["end"] - c["start"])))
    taken: list[tuple[int, int]] = []
    accepted = []
    for cand in candidates:
        if _spans_overlap(cand["start"], cand["end"], taken):
            continue
        taken.append((cand["start"], cand["end"]))
        accepted.append(cand)
    accepted.sort(key=lambda c: (c["start"], c["end"]))

    backend = "spacy_ner+rules" if nlp is not None else "rules_only"
    entities = []
    for i, cand in enumerate(accepted, 1):
        entities.append({
            "id": f"temp_{i:03d}",
            "type": cand["type"],
            "value": cand["value"],
            "confidence": cand["confidence"],
            "normalized_value": _normalize_for(cand["type"], cand["value"]),
            "raw_text": cand["raw_text"],
            "method": cand["method"],
            "nlp_backend": backend,
        })
    return {"document_id": document_id, "entities": entities,
            "relationships": []}


def structured_entity(entity_type: str, value: str, source_field: str) -> dict:
    """Wrap an already-structured identifier (e.g. a CDR caller) as an
    extraction result with full confidence — no NLP needed, same shape."""
    if entity_type not in ENTITY_TYPES:
        raise IngestionError("INVALID_RECORD_STRUCTURE",
                             f"Unknown entity type: {entity_type}",
                             http_status=422)
    return {"id": "temp_000", "type": entity_type, "value": value,
            "confidence": _CONF["structured"],
            "normalized_value": _normalize_for(entity_type, value),
            "raw_text": value,
            "method": f"structured_field:{source_field}",
            "nlp_backend": "structured"}
