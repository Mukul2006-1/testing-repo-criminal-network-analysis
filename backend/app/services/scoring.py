"""Phase 5 — Investigation Priority Score (PROJECT_SPEC.md §9).

Formula (fixed, v1)::

    priority_score = 0.35 * PageRank + 0.35 * Betweenness + 0.30 * Anomaly

All components are normalized to [0, 1] before combining. The result is a
triage aid that orders entities for investigator review. It is called
"Investigation Priority Score" and must never be called criminal/guilt/
crime/threat probability — the words do not appear in this module except
in this paragraph.

Score reasons are generated from actual component values only; causality
is never claimed.
"""

from __future__ import annotations

from .centrality import sanitize_score
from .validation import IngestionError

WEIGHT_PAGERANK = 0.35
WEIGHT_BETWEENNESS = 0.35
WEIGHT_ANOMALY = 0.30
FORMULA = "0.35 × PageRank + 0.35 × Betweenness + 0.30 × Anomaly Score"
FORMULA_VERSION = "v1"
DISCLAIMER = ("Investigation-priority indicator only. Not probability of "
              "criminality, guilt, proof of criminal activity, or "
              "future-crime prediction.")

PR_THRESHOLD = 0.7
BW_THRESHOLD = 0.7
ANOMALY_THRESHOLD = 0.7


def _component(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IngestionError("INVALID_SCORE",
                             f"{name} must be numeric.",
                             http_status=422) from exc
    return sanitize_score(number)


def priority_score(pagerank: float, betweenness: float,
                   anomaly: float) -> dict:
    """Combine normalized components. Returns::

        {"score": [0,1] rounded to 4dp, "priority": int 0-100,
         "components": {...}, "reasons": [...]}
    """
    pr = _component(pagerank, "pagerank")
    bw = _component(betweenness, "betweenness")
    an = _component(anomaly, "anomaly")
    score = round(WEIGHT_PAGERANK * pr + WEIGHT_BETWEENNESS * bw +
                  WEIGHT_ANOMALY * an, 4)
    return {"score": score, "priority": int(round(score * 100)),
            "components": {"pagerank": pr, "betweenness": bw,
                           "anomaly_score": an},
            "reasons": explain_score(pr, bw, an)}


def explain_score(pagerank: float, betweenness: float, anomaly: float,
                  high_degree: bool = False,
                  community_size: int = 0) -> list[str]:
    """Reasons drawn strictly from the supplied values."""
    reasons = []
    if pagerank >= PR_THRESHOLD:
        reasons.append("High structural importance in the network")
    if betweenness >= BW_THRESHOLD:
        reasons.append("Acts as a bridge between network groups")
    if anomaly >= ANOMALY_THRESHOLD:
        reasons.append("Unusual activity pattern")
    if high_degree:
        reasons.append("Highly connected entity")
    if community_size >= 3:
        reasons.append("Connected to a dense network group")
    return reasons
