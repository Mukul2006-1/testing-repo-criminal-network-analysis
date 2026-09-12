"""Phase 5 — analytics orchestration (read-mostly, demo scale).

``run_analytics`` ties the phases together for one scoring run:

1. centrality + communities over a graph edge snapshot,
2. per-PERSON activity features from processed records,
3. Isolation Forest anomaly scores,
4. priority scores (computed on read, not stored),
5. persistence of analytics + anomalies + run metadata.

Read-only guarantees: resolution memory and canonical entities are never
modified here. FIR location observations match canonical entities by exact
normalized lookup only — unmatched names are skipped, never invented, and
no mentions are written. Unknown phones/accounts in CDR/transactions are
skipped with the same discipline (contacts may still be counted by phone
identifier, documented in the anomaly module).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import anomaly as anomaly_mod
from . import centrality as centrality_mod
from . import communities as communities_mod
from . import nlp as nlp_mod
from . import scoring as scoring_mod


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _person_maps(store):
    """Phone/account number -> person canonical id from stored attributes."""
    phones, accounts = {}, {}
    for person in store.list_entities_by_type("PERSON"):
        attrs = person.get("attributes") or {}
        for number in attrs.get("phones", []) or []:
            phones.setdefault(str(number), person["id"])
        for account in attrs.get("accounts", []) or []:
            accounts.setdefault(str(account), person["id"])
    return phones, accounts


def _exact_person(store, normalized_value: str) -> str | None:
    found = store.find_entities_by_normalized("PERSON", normalized_value)
    return found[0]["id"] if found else None


def collect_events(store, record_files: list[tuple[str, list[dict]]]) -> dict:
    """Split processed records into person-keyed activity events.

    Returns ``{"calls": {pid: [...]}, "txns": {pid: [...]},
    "locs": {pid: [...]}}`` with call legs ``{timestamp, duration,
    contact}``, txn legs ``{timestamp, amount}`` and location observations
    ``{date, location}``.
    """
    phones, accounts = _person_maps(store)
    calls: dict[str, list[dict]] = {}
    txns: dict[str, list[dict]] = {}
    locs: dict[str, list[dict]] = {}

    def add(mapping, pid, event):
        mapping.setdefault(pid, []).append(event)

    for _, records in record_files:
        for record in records:
            normalized = record.get("normalized") or {}
            source_type = record.get("source_type")
            source_id = record.get("source_id", "")
            if source_type == "CDR":
                caller, receiver = (normalized.get("caller"),
                                    normalized.get("receiver"))
                if not caller or not receiver:
                    continue
                pid_a, pid_b = phones.get(str(caller)), \
                    phones.get(str(receiver))
                event = {"timestamp": normalized.get("timestamp", ""),
                         "duration": normalized.get("duration", 0)}
                if pid_a:
                    add(calls, pid_a, {**event, "contact": pid_b or
                                       str(receiver)})
                if pid_b:
                    add(calls, pid_b, {**event, "contact": pid_a or
                                       str(caller)})
            elif source_type == "TRANSACTION":
                sender, receiver = (normalized.get("sender_account"),
                                    normalized.get("receiver_account"))
                event = {"timestamp": normalized.get("timestamp", ""),
                         "amount": normalized.get("amount", 0)}
                if sender and accounts.get(str(sender)):
                    add(txns, accounts[str(sender)], event)
                if receiver and accounts.get(str(receiver)):
                    add(txns, accounts[str(receiver)], event)
            elif source_type == "FIR":
                text = normalized.get("text", "")
                date = normalized.get("date", "")
                if not text or not date:
                    continue
                extraction = nlp_mod.extract_entities(text, source_id)
                persons = {pid for entity in extraction["entities"]
                           if entity["type"] == "PERSON"
                           for pid in [_exact_person(
                               store, entity["normalized_value"])]
                           if pid}
                locations = [entity["value"] for entity in
                             extraction["entities"]
                             if entity["type"] == "LOCATION"]
                for pid in persons:
                    for location in locations:
                        add(locs, pid, {"date": date, "location": location})
    return {"calls": calls, "txns": txns, "locs": locs}


def analytics_summary_for(store, entity_id: str) -> dict | None:
    """Stored analytics + computed priority for one entity (None if never
    scored). Priority is derived deterministically, never stored."""
    metric = store.get_analytics(entity_id)
    anomaly = store.latest_anomaly(entity_id)
    if metric is None and anomaly is None:
        return None
    pr = float(metric["pagerank"]) if metric else 0.0
    bw = float(metric["betweenness"]) if metric else 0.0
    an = float(anomaly["score"]) if anomaly else 0.0
    result = scoring_mod.priority_score(pr, bw, an)
    return {"degree": int(metric["degree"]) if metric else 0,
            "pagerank": pr, "betweenness": bw,
            "community_id": metric.get("community_id") if metric else None,
            "anomaly_score": an, "priority_score": result["score"]}


def run_analytics(store, nodes: list[dict], edges: list[tuple[str, str]],
                  record_files: list[tuple[str, list[dict]]],
                  run_id: str | None = None) -> dict:
    """Execute one scoring run and persist results. Returns a summary."""
    run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
    node_ids = [node["id"] for node in nodes]
    adjacency = centrality_mod.build_adjacency(node_ids, edges)
    metrics = centrality_mod.analyze(adjacency)
    partition = communities_mod.louvain(adjacency)
    sizes = communities_mod.community_sizes(partition)

    events = collect_events(store, record_files)
    window = anomaly_mod.observation_window_days(
        [call for legs in events["calls"].values() for call in legs],
        [txn for legs in events["txns"].values() for txn in legs],
        [{"date": obs["date"]}
         for legs in events["locs"].values() for obs in legs])

    persons = sorted(entity["id"]
                     for entity in store.list_entities_by_type("PERSON"))
    feature_rows = []
    for pid in persons:
        features = anomaly_mod.features_for_person(
            events["calls"].get(pid, []), events["txns"].get(pid, []),
            events["locs"].get(pid, []), window)
        feature_rows.append({"entity_id": pid, **features})
    anomalies = {row["entity_id"]: row
                 for row in anomaly_mod.detect(feature_rows)}
    created_at = _now()
    for pid in persons:
        metric = metrics.get(pid, {"degree": 0, "pagerank": 0.0,
                                   "betweenness": 0.0})
        store.upsert_analytics({
            "entity_id": pid, "degree": metric["degree"],
            "pagerank": metric["pagerank"],
            "betweenness": metric["betweenness"],
            "community_id": partition.get(pid), "run_id": run_id,
            "updated_at": created_at})
        anomaly = anomalies.get(pid)
        if anomaly is not None:
            store.save_anomaly({
                "id": f"anom_{uuid.uuid4().hex[:8]}", "entity_id": pid,
                "score": anomaly["anomaly_score"],
                "severity": anomaly["severity"],
                "reason": "; ".join(anomaly["reasons"]) or "No anomaly signal",
                "features": anomaly["features"],
                "model_version": anomaly["model_version"],
                "created_at": created_at})
    store.record_analytics_run({
        "id": run_id, "created_at": created_at,
        "node_count": len(node_ids), "edge_count": len(edges),
        "methods": {"centrality": "degree/pagerank/brandes-undirected",
                    "communities": "louvain",
                    "anomaly": anomaly_mod.MODEL_VERSION,
                    "scoring": scoring_mod.FORMULA_VERSION,
                    "window_days": window}})

    ranked = []
    for pid in persons:
        metric = metrics.get(pid, {"pagerank": 0.0, "betweenness": 0.0})
        anomaly = anomalies.get(pid, {"anomaly_score": 0.0})
        result = scoring_mod.priority_score(
            metric["pagerank"], metric["betweenness"],
            anomaly["anomaly_score"])
        ranked.append({"entity_id": pid,
                       "priority_score": result["score"]})
    ranked.sort(key=lambda item: (-item["priority_score"],
                                  item["entity_id"]))
    return {"run_id": run_id, "node_count": len(node_ids),
            "edge_count": len(edges), "entities_scored": len(persons),
            "window_days": window, "top": ranked[:5]}
