"""Phase 2 — deterministic normalization (standard library only).

Every normalizer is a pure function: same input -> same output, no I/O, no
guessing. The original value is always preserved by the caller (see
`ingestion.STANDARDIZED_RECORD_CONTRACT`); normalizers only derive the
canonical form and raise field errors with explicit codes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .validation import IngestionError

PHONE_RE = re.compile(r"^\+91\d{10}$")
VEHICLE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$")

_TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_name(value: str) -> str:
    """Display form: trimmed, single-spaced, semantics unchanged."""
    return normalize_whitespace(str(value))


def normalized_name_key(value: str) -> str:
    """Match/search key: lowercase collapsed form (cf. DATABASE_SCHEMA)."""
    return normalize_whitespace(str(value)).lower()


def normalize_phone(value: object) -> str:
    """Canonical Indian MSISDN: "+91" + 10 digits.

    Accepts "+91 98765 43210", "+91-98765-43210", "(+91) 9876543210",
    "919876543210" and bare 10-digit mobile numbers. Anything else is an
    explicit INVALID_PHONE_NUMBER — never silently coerced.
    """
    text = re.sub(r"[\s\-().]", "", str(value))
    if text.startswith("+"):
        digits = text[1:]
        if not digits.isdigit():
            raise ValueError(f"non-numeric phone: {value!r}")
        if len(digits) == 12 and digits.startswith("91"):
            canonical = f"+{digits}"
        elif len(digits) == 10:
            canonical = f"+91{digits}"
        else:
            raise ValueError(f"unexpected phone length: {value!r}")
    else:
        if not text.isdigit():
            raise ValueError(f"non-numeric phone: {value!r}")
        if len(text) == 12 and text.startswith("91"):
            canonical = f"+{text}"
        elif len(text) == 10:
            canonical = f"+91{text}"
        else:
            raise ValueError(f"unexpected phone length: {value!r}")
    if not PHONE_RE.match(canonical):
        raise ValueError(f"phone outside +91XXXXXXXXXX format: {value!r}")
    return canonical


def normalize_vehicle(value: object) -> str:
    """"DL 01 AB 1234" / "dl-01-ab-1234" -> "DL01AB1234"."""
    canonical = re.sub(r"[\s\-]", "", str(value)).upper()
    if not VEHICLE_RE.match(canonical):
        raise ValueError(f"vehicle registration format not recognized: {value!r}")
    return canonical


def normalize_account(value: object) -> str:
    """"acc 001" / "acc-001" -> "ACC001". Canonical form is uppercase,
    spaceless alphanumeric (3-32 chars)."""
    canonical = re.sub(r"[\s\-]", "", str(value)).upper()
    if not re.fullmatch(r"[A-Z0-9]{3,32}", canonical):
        raise ValueError(f"account format not recognized: {value!r}")
    return canonical


def normalize_timestamp(value: object) -> str:
    """Any supported timestamp -> "YYYY-MM-DDTHH:MM:SSZ" (UTC)."""
    text = str(value).strip().replace("Z", "").strip()
    if not text:
        raise ValueError("empty timestamp")
    parsed: datetime | None = None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"unsupported timestamp: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_date(value: object) -> str:
    """Any supported date/timestamp -> "YYYY-MM-DD" (cf. DATE entities)."""
    return normalize_timestamp(value)[:10]


def normalize_amount(value: object) -> float | int:
    try:
        amount = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric amount: {value!r}") from exc
    if amount <= 0:
        raise ValueError(f"amount must be > 0: {value!r}")
    return int(amount) if amount.is_integer() else amount


def normalize_int(value: object, field: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer: {value!r}") from exc


def normalize_duration(value: object) -> int:
    duration = normalize_int(value, "duration")
    if duration < 0:
        raise ValueError(f"duration must be >= 0: {value!r}")
    return duration


def _norm(rule, value, errors: list, record_index: int, field: str,
          code: str, optional: bool = False):
    """Apply one normalizer; collect a structured field error on failure."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if optional:
            return None
        errors.append({"record": record_index, "field": field,
                       "issue": "missing required field", "code": code})
        return None
    try:
        return rule(value)
    except ValueError as exc:
        errors.append({"record": record_index, "field": field,
                       "issue": str(exc), "code": code})
        return None


# Per-type normalization plans: field -> (rule, code, optional).
PLANS: dict[str, dict[str, tuple]] = {
    "FIR": {
        "fir_id": (lambda v: normalize_whitespace(str(v)), "INVALID_RECORD_STRUCTURE", False),
        "date": (normalize_date, "INVALID_TIMESTAMP", False),
        "police_station": (normalize_name, "INVALID_RECORD_STRUCTURE", True),
        "text": (normalize_whitespace, "INVALID_RECORD_STRUCTURE", False),
        "source": (lambda v: normalize_whitespace(str(v)).upper(), "INVALID_RECORD_STRUCTURE", True),
    },
    "CDR": {
        "cdr_id": (lambda v: normalize_whitespace(str(v)), "INVALID_RECORD_STRUCTURE", False),
        "caller": (normalize_phone, "INVALID_PHONE_NUMBER", False),
        "receiver": (normalize_phone, "INVALID_PHONE_NUMBER", False),
        "timestamp": (normalize_timestamp, "INVALID_TIMESTAMP", False),
        "duration": (normalize_duration, "INVALID_NUMERIC_VALUE", False),
    },
    "TRANSACTION": {
        "transaction_id": (lambda v: normalize_whitespace(str(v)), "INVALID_RECORD_STRUCTURE", False),
        "sender_account": (lambda v: normalize_whitespace(str(v)).upper(), "INVALID_RECORD_STRUCTURE", False),
        "receiver_account": (lambda v: normalize_whitespace(str(v)).upper(), "INVALID_RECORD_STRUCTURE", False),
        "amount": (normalize_amount, "INVALID_NUMERIC_VALUE", False),
        "currency": (lambda v: normalize_whitespace(str(v)).upper(), "INVALID_RECORD_STRUCTURE", False),
        "timestamp": (normalize_timestamp, "INVALID_TIMESTAMP", False),
    },
    "VEHICLE": {
        "vehicle_id": (lambda v: normalize_whitespace(str(v)), "INVALID_RECORD_STRUCTURE", False),
        "registration_number": (normalize_vehicle, "INVALID_VEHICLE_NUMBER", False),
        "owner_name": (normalize_name, "INVALID_RECORD_STRUCTURE", False),
        "source": (lambda v: normalize_whitespace(str(v)).upper(), "INVALID_RECORD_STRUCTURE", True),
    },
    "LOCATION": {
        "location_id": (lambda v: normalize_whitespace(str(v)), "INVALID_RECORD_STRUCTURE", False),
        "name": (normalize_name, "INVALID_RECORD_STRUCTURE", False),
        "latitude": (lambda v: float(str(v).strip()), "INVALID_NUMERIC_VALUE", True),
        "longitude": (lambda v: float(str(v).strip()), "INVALID_NUMERIC_VALUE", True),
    },
}


def normalize_record(dataset_type: str, record: dict,
                     record_index: int) -> tuple[dict, list[dict]]:
    """Normalize one record. Returns (normalized, field_errors).

    Adds derived match keys without touching semantics:
    - owner_name -> owner_normalized ; name -> name_normalized
    """
    plan = PLANS[dataset_type]
    normalized: dict = {}
    errors: list[dict] = []
    source = record if isinstance(record, dict) else {}
    for field, (rule, code, optional) in plan.items():
        value = _norm(rule, source.get(field), errors, record_index,
                      field, code, optional)
        if value is not None or not optional:
            normalized[field] = value
    if dataset_type == "VEHICLE" and normalized.get("owner_name"):
        normalized["owner_normalized"] = normalized_name_key(
            normalized["owner_name"])
    if dataset_type == "LOCATION" and normalized.get("name"):
        normalized["name_normalized"] = normalized_name_key(
            normalized["name"])
    return normalized, errors
