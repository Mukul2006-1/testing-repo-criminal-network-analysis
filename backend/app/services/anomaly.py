"""Phase 5 — behavioral anomaly detection (Isolation Forest, scikit-learn).

Fixed v1 feature set per entity (PROJECT_SPEC.md §8):

    calls_per_day, unique_contacts, average_call_duration, night_calls,
    transaction_count, transaction_amount, unique_locations, location_changes

Window definition (pinned here for v1): the observation window is the
number of distinct UTC dates spanned by ALL events supplied to a run
(minimum 1 day). Rates (calls_per_day) divide by that window.

Location observations are FIR co-mentions: a (person, location, date)
triple from a FIR naming both. This is documented as document-level
evidence, not GPS tracking. Persons with no location observations score
0 on both location features with no reason emitted — missing data is
never fabricated.

Small-data contract: empty input -> []; a single entity or a constant
feature matrix cannot support Isolation Forest -> safe default
(score 0.0, LOW, explanatory reason). No NaN/Infinity ever escapes:
every float is sanitized to a finite [0, 1]-compatible value.

Anomaly scores are behavioral signals for triage. They are not, and must
never be labeled as, probability of criminality.
"""

from __future__ import annotations

import math
from datetime import datetime

from .centrality import sanitize_score
from .validation import IngestionError

FEATURES = (
    "calls_per_day",
    "unique_contacts",
    "average_call_duration",
    "night_calls",
    "transaction_count",
    "transaction_amount",
    "unique_locations",
    "location_changes",
)

MODEL_VERSION = "iforest_v1"
DEFAULT_CONTAMINATION = 0.15
DEFAULT_RANDOM_STATE = 42
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 5  # [00:00, 05:00): night window (UTC, documented)


def _finite(number: object, default: float = 0.0) -> float:
    try:
        value = float(number)
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value


def _day_key(timestamp: str) -> str:
    try:
        return datetime.strptime(timestamp[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


def _hour(timestamp: str) -> int | None:
    try:
        return datetime.strptime(timestamp[11:13], "%H").hour
    except (ValueError, TypeError, IndexError):
        return None


def observation_window_days(call_events: list[dict],
                            txn_events: list[dict],
                            loc_observations: list[dict]) -> int:
    """Distinct UTC dates across all events (minimum 1)."""
    days = {day for events in (call_events, txn_events)
            for event in events
            for day in [_day_key(str(event.get("timestamp", "")))] if day}
    days.update(_day_key(str(obs.get("date", "")))
                for obs in loc_observations)
    days.discard("")
    return max(1, len(days))


def features_for_person(person_calls: list[dict], person_txns: list[dict],
                        person_locs: list[dict],
                        window_days: int) -> dict[str, float]:
    """Aggregate one entity's raw events into the 8 fixed features."""
    window = max(1, int(window_days or 1))
    durations = [_finite(call.get("duration"), 0.0)
                 for call in person_calls if call.get("duration") is not None]
    contacts = {str(call.get("contact")) for call in person_calls
                if call.get("contact")}
    night = sum(1 for call in person_calls
                if (_hour(str(call.get("timestamp", ""))) is not None
                    and NIGHT_START_HOUR
                    <= _hour(str(call.get("timestamp", ""))) < NIGHT_END_HOUR))
    amounts = [_finite(txn.get("amount"), 0.0) for txn in person_txns]
    ordered_locs = sorted(
        {(str(obs.get("date", "")), str(obs.get("location", "")))
         for obs in person_locs if obs.get("location")})
    distinct_locs = {loc for _, loc in ordered_locs}
    changes = sum(1 for prev, current in
                  zip([loc for _, loc in ordered_locs],
                      [loc for _, loc in ordered_locs][1:])
                  if prev != current)
    calls = len(person_calls)
    return {
        "calls_per_day": round(calls / window, 2),
        "unique_contacts": float(len(contacts)),
        "average_call_duration": round(sum(durations) / len(durations), 2)
        if durations else 0.0,
        "night_calls": float(night),
        "transaction_count": float(len(person_txns)),
        "transaction_amount": round(sum(amounts), 2),
        "unique_locations": float(len(distinct_locs)),
        "location_changes": float(changes),
    }


def _medians(rows: list[dict[str, float]]) -> dict[str, float]:
    medians = {}
    for feature in FEATURES:
        ordered = sorted(_finite(row.get(feature)) for row in rows)
        count = len(ordered)
        if count == 0:
            medians[feature] = 0.0
        elif count % 2:
            medians[feature] = ordered[count // 2]
        else:
            medians[feature] = (ordered[count // 2 - 1] + ordered[count // 2]) / 2.0
    return medians


def explain_anomaly(features: dict[str, float],
                    medians: dict[str, float]) -> list[str]:
    """Evidence-backed reasons only: each reason fires iff the entity's
    feature is elevated against the run median. No evidence -> no reason."""
    reasons = []
    get = lambda name: _finite(features.get(name))
    med = lambda name: _finite(medians.get(name))
    if get("calls_per_day") > 0 and get("calls_per_day") >= max(2.0, 2 * med("calls_per_day")):
        reasons.append("Communication spike")
    if get("unique_contacts") >= max(5.0, 2 * med("unique_contacts")) and get("unique_contacts") > 0:
        reasons.append("High number of unique contacts")
    if get("night_calls") >= max(3.0, 2 * med("night_calls")) and get("night_calls") > 0:
        reasons.append("Unusual night-call activity")
    if get("transaction_amount") >= max(100000.0, 3 * med("transaction_amount")) and get("transaction_amount") > 0:
        reasons.append("Large transaction activity")
    if get("transaction_count") >= max(5.0, 2 * med("transaction_count")) and get("transaction_count") > 0:
        reasons.append("Unusual transaction frequency")
    if get("location_changes") >= max(3.0, 2 * med("location_changes")) and get("location_changes") > 0:
        reasons.append("Unusual location changes")
    if get("unique_locations") >= max(4.0, 2 * med("unique_locations")) and get("unique_locations") > 0:
        reasons.append("High location diversity")
    return reasons


def severity_for(score: float) -> str:
    """Fixed mapping (API_SPEC.md §6): >=0.8 HIGH, >=0.5 MEDIUM, else LOW."""
    if score >= 0.8:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


def _default_result(entity_id: str, features: dict[str, float],
                    reason: str) -> dict:
    return {"entity_id": entity_id,
            "features": {name: _finite(features.get(name)) for name in FEATURES},
            "anomaly_score": 0.0, "severity": "LOW", "reasons": [reason],
            "model_version": MODEL_VERSION}


def detect(feature_rows: list[dict],
           contamination: float = DEFAULT_CONTAMINATION,
           random_state: int = DEFAULT_RANDOM_STATE) -> list[dict]:
    """Run Isolation Forest over per-entity feature rows.

    Each row: ``{"entity_id": ..., <8 feature names>}``. Returns one result
    per row: ``{entity_id, features, anomaly_score [0,1], severity, reasons,
    model_version}`` in input order. Deterministic for a fixed random_state.
    """
    if not isinstance(contamination, (int, float)) or \
            not 0.0 < float(contamination) <= 0.5:
        raise IngestionError("INVALID_CONTAMINATION",
                             "contamination must be in (0, 0.5].",
                             http_status=422)
    results = []
    if not feature_rows:
        return results
    medians = _medians([{name: row.get(name) for name in FEATURES}
                        for row in feature_rows])
    if len(feature_rows) == 1:
        row = feature_rows[0]
        result = _default_result(
            row.get("entity_id", ""),
            {name: row.get(name) for name in FEATURES},
            "Insufficient data for anomaly detection (single entity)")
        results.append(result)
        return results

    matrix = [[_finite(row.get(name)) for name in FEATURES]
              for row in feature_rows]
    if all(row == matrix[0] for row in matrix):
        for row in feature_rows:
            results.append(_default_result(
                row.get("entity_id", ""),
                {name: row.get(name) for name in FEATURES},
                "Insufficient data for anomaly detection "
                "(constant features)"))
        return results

    from sklearn.ensemble import IsolationForest

    model = IsolationForest(contamination=float(contamination),
                            random_state=random_state)
    raw = [-float(value) for value in
           model.fit(matrix).score_samples(matrix)]
    floor, ceiling = min(raw), max(raw)
    if ceiling <= floor:
        scores = [0.0 for _ in raw]
    else:
        scores = [sanitize_score((value - floor) / (ceiling - floor))
                  for value in raw]
    for row, score in zip(feature_rows, scores):
        features = {name: _finite(row.get(name)) for name in FEATURES}
        reasons = explain_anomaly(features, medians)
        results.append({"entity_id": row.get("entity_id", ""),
                        "features": features, "anomaly_score": score,
                        "severity": severity_for(score), "reasons": reasons,
                        "model_version": MODEL_VERSION})
    return results
