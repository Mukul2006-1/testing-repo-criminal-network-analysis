"""Tamper-evident audit log (PROJECT_SPEC.md §17).

Each event appends ``SHA-256(prev_hash || canonical_event_payload)`` with
actor, action, timestamp and input/output hashes. Verification recomputes
the whole chain; any edit, deletion or reorder breaks it loudly.

This is an append-only, single-server hash chain — it proves local
tampering, not decentralized consensus. Never claim blockchain equivalence.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from .validation import IngestionError

GENESIS_HASH = "GENESIS"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(value: object) -> str:
    """Stable SHA-256 hex of a small JSON-encodable value (or raw string)."""
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def event_hash(prev_hash: str, created_at: str, actor: str, action: str,
               target: str, input_hash: str, output_hash: str) -> str:
    """Chain hash: SHA-256 over the canonical event payload."""
    payload = json.dumps({
        "prev_hash": prev_hash, "created_at": created_at, "actor": actor,
        "action": action, "target": target or "",
        "input_hash": input_hash or "", "output_hash": output_hash or "",
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def record(store, *, actor: str, action: str, target: str = "",
           input_hash: str = "", output_hash: str = "") -> dict:
    """Append one audit event and return it (raises on persistence failure)."""
    if not actor or not action:
        raise IngestionError("AUDIT_EVENT_INVALID",
                             "Audit record requires actor and action.",
                             http_status=500)
    prev = store.latest_audit_hash()
    created = _now()
    entry = {
        "id": f"audit_{uuid.uuid4().hex[:12]}",
        "created_at": created,
        "actor": str(actor)[:256],
        "action": str(action)[:64],
        "target": str(target or "")[:256],
        "input_hash": str(input_hash or "")[:128],
        "output_hash": str(output_hash or "")[:128],
        "prev_hash": prev,
        "hash": event_hash(prev, created, str(actor)[:256],
                           str(action)[:64], str(target or "")[:256],
                           str(input_hash or "")[:128],
                           str(output_hash or "")[:128]),
    }
    try:
        store.append_audit(entry)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError("AUDIT_WRITE_FAILED",
                             "Audit trail write failed.",
                             http_status=500) from exc
    return entry


def verify(store, limit: int = 10000) -> dict:
    """Recompute the chain. Returns verified/count/head_hash/broken_at."""
    entries = store.list_audit(limit=limit)
    prev = GENESIS_HASH
    for entry in entries:
        expected = event_hash(
            entry["prev_hash"], entry["created_at"], entry["actor"],
            entry["action"], entry.get("target", ""),
            entry.get("input_hash", ""), entry.get("output_hash", ""))
        if entry["prev_hash"] != prev or expected != entry["hash"]:
            return {"verified": False, "count": len(entries),
                    "head_hash": entries[-1]["hash"] if entries else None,
                    "broken_at": entry["id"]}
        prev = entry["hash"]
    return {"verified": True, "count": len(entries),
            "head_hash": entries[-1]["hash"] if entries else None,
            "broken_at": None}
