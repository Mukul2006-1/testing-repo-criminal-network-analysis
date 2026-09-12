"""Phase 2 — document/job persistence (standard library sqlite3).

Mirrors DATABASE_SCHEMA.md §3 (documents) for local development and tests:
id, type, filename, source, uploaded_by, uploaded_at, status, file_hash,
metadata (JSON). Production PostgreSQL wiring (with the users FK, CITEXT
email, and hash-chain audit_logs) lands with later phases; this store keeps
the same columns, status vocabulary (UPLOADED | VALIDATING | PROCESSING |
PROCESSED | FAILED), and append-oriented discipline so the swap is mechanical.

- All SQL is parameterized; no caller input ever touches a query string.
- Multi-row mutations commit atomically; callers must treat an exception as
  "not persisted" and never report success.
- `uploaded_by` defaults to "system"; the FK to users is enforced once the
  users table exists (Phase 6 auth).
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3

STATUSES = ("UPLOADED", "VALIDATING", "PROCESSING", "PROCESSED", "FAILED")
USER_ROLES = ("INVESTIGATOR", "SENIOR_INVESTIGATOR", "ADMIN")


def default_db_path() -> str:
    """Production default store location (overridable via DOCUMENT_DB_PATH)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(repo_root, "data", "processed", "documents.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  filename TEXT NOT NULL,
  source TEXT,
  uploaded_by TEXT NOT NULL DEFAULT 'system',
  uploaded_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'UPLOADED',
  file_hash TEXT NOT NULL UNIQUE,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  upload_id TEXT NOT NULL,
  status TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('PERSON','PHONE','LOCATION','VEHICLE',
    'ORGANIZATION','DATE','ACCOUNT')),
  canonical_name TEXT NOT NULL CHECK (length(canonical_name) BETWEEN 1 AND 256),
  normalized_name TEXT NOT NULL CHECK (length(normalized_name) BETWEEN 1 AND 256),
  attributes TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_type_norm
  ON entities(type, normalized_name);
CREATE TABLE IF NOT EXISTS entity_mentions (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entities(id),
  document_id TEXT NOT NULL,
  text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 1000),
  confidence REAL CHECK (confidence BETWEEN 0 AND 1),
  extraction_method TEXT CHECK (extraction_method IS NULL
    OR length(extraction_method) BETWEEN 1 AND 64),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_mentions_document ON entity_mentions(document_id);
CREATE TABLE IF NOT EXISTS counters (
  prefix TEXT PRIMARY KEY,
  next_n INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entity_analytics (
  entity_id TEXT PRIMARY KEY REFERENCES entities(id),
  degree INTEGER NOT NULL DEFAULT 0,
  pagerank REAL NOT NULL DEFAULT 0.0,
  betweenness REAL NOT NULL DEFAULT 0.0,
  community_id INTEGER,
  run_id TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS anomalies (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entities(id),
  score REAL NOT NULL CHECK (score BETWEEN 0 AND 1),
  severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH')),
  reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
  features TEXT NOT NULL DEFAULT '{}',
  model_version TEXT NOT NULL CHECK (length(model_version) BETWEEN 1 AND 64),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anomalies_entity ON anomalies(entity_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);
CREATE TABLE IF NOT EXISTS analytics_runs (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  node_count INTEGER NOT NULL DEFAULT 0,
  edge_count INTEGER NOT NULL DEFAULT 0,
  methods TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 128),
  email TEXT NOT NULL UNIQUE CHECK (length(email) BETWEEN 3 AND 256),
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('INVESTIGATOR','SENIOR_INVESTIGATOR',
    'ADMIN')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
"""


class DocumentStore:
    def __init__(self, db_path: str) -> None:
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.db_path = db_path
        with self._session() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _session(self):
        """Yield a connection that always commits-or-rolls-back and closes.

        Note: sqlite3.Connection as a context manager does NOT close the
        handle — without this wrapper, file locks leak (notably on Windows).
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _doc(row: sqlite3.Row) -> dict:
        doc = dict(row)
        doc["metadata"] = json.loads(doc["metadata"] or "{}")
        return doc

    # -- documents ------------------------------------------------------
    def create_document(self, document: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO documents (id, type, filename, source, "
                "uploaded_by, uploaded_at, status, file_hash, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document["id"], document["type"], document["filename"],
                 document.get("source"), document.get("uploaded_by", "system"),
                 document["uploaded_at"], document["status"],
                 document["file_hash"], json.dumps(document.get("metadata") or {})),
            )

    def get_document(self, upload_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?",
                               (upload_id,)).fetchone()
        return self._doc(row) if row else None

    def update_status(self, upload_id: str, status: str,
                      metadata_patch: dict | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self._session() as conn:
            row = conn.execute("SELECT metadata FROM documents WHERE id = ?",
                               (upload_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown document: {upload_id}")
            metadata = json.loads(row["metadata"] or "{}")
            metadata.update(metadata_patch or {})
            conn.execute("UPDATE documents SET status = ?, metadata = ? "
                         "WHERE id = ?",
                         (status, json.dumps(metadata), upload_id))

    def find_by_hash(self, file_hash: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM documents WHERE file_hash = ?",
                               (file_hash,)).fetchone()
        return self._doc(row) if row else None

    # -- jobs --------------------------------------------------------------
    def create_job(self, job: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO jobs (id, upload_id, status, result, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (job["id"], job["upload_id"], job["status"], "{}",
                 job["created_at"], job["created_at"]),
            )

    def update_job(self, job_id: str, status: str, result: dict) -> None:
        with self._session() as conn:
            conn.execute("UPDATE jobs SET status = ?, result = ?, "
                         "updated_at = ? WHERE id = ?",
                         (status, json.dumps(result),
                          result.get("created_at", ""), job_id))

    def get_job(self, job_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?",
                               (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["result"] = json.loads(job["result"] or "{}")
        return job

    # -- entities / mentions (Phase 3; mirrors DATABASE_SCHEMA.md §§4-5) --
    def create_entity(self, entity: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO entities (id, type, canonical_name, "
                "normalized_name, attributes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entity["id"], entity["type"], entity["canonical_name"],
                 entity["normalized_name"],
                 json.dumps(entity.get("attributes") or {}),
                 entity.get("created_at", ""),
                 entity.get("updated_at", entity.get("created_at", ""))),
            )

    @staticmethod
    def _entity(row: sqlite3.Row) -> dict:
        entity = dict(row)
        entity["attributes"] = json.loads(entity["attributes"] or "{}")
        return entity

    def get_entity(self, entity_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?",
                               (entity_id,)).fetchone()
        return self._entity(row) if row else None

    def find_entities_by_normalized(self, entity_type: str,
                                    normalized_name: str) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM entities WHERE type = ? AND "
                "normalized_name = ? ORDER BY created_at, id",
                (entity_type, normalized_name)).fetchall()
        return [self._entity(r) for r in rows]

    def list_entities_by_type(self, entity_type: str) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY created_at, id",
                (entity_type,)).fetchall()
        return [self._entity(r) for r in rows]

    def update_entity_attrs(self, entity_id: str, attributes: dict) -> None:
        with self._session() as conn:
            conn.execute("UPDATE entities SET attributes = ? WHERE id = ?",
                         (json.dumps(attributes or {}), entity_id))

    def create_mention(self, mention: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO entity_mentions (id, entity_id, document_id, "
                "text, confidence, extraction_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mention["id"], mention["entity_id"], mention["document_id"],
                 mention["text"], mention.get("confidence"),
                 mention.get("extraction_method"),
                 mention.get("created_at", "")),
            )

    def list_mentions(self, entity_id: str, limit: int = 10) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM entity_mentions WHERE entity_id = ? "
                "ORDER BY confidence DESC, id LIMIT ?",
                (entity_id, max(1, min(limit, 100)))).fetchall()
        return [dict(r) for r in rows]

    def next_counter(self, prefix: str) -> int:
        """Atomically reserve the next canonical-ID sequence number."""
        with self._session() as conn:
            row = conn.execute("SELECT next_n FROM counters WHERE prefix = ?",
                               (prefix,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO counters (prefix, next_n) "
                             "VALUES (?, 2)", (prefix,))
                return 1
            conn.execute("UPDATE counters SET next_n = next_n + 1 "
                         "WHERE prefix = ?", (prefix,))
            return int(row["next_n"])

    # -- analytics (Phase 5; mirrors DATABASE_SCHEMA.md §7) ---------------
    def upsert_analytics(self, row: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO entity_analytics (entity_id, degree, pagerank, "
                "betweenness, community_id, run_id, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(entity_id) DO UPDATE SET degree=excluded.degree,"
                "pagerank=excluded.pagerank,betweenness=excluded.betweenness,"
                "community_id=excluded.community_id,run_id=excluded.run_id,"
                "updated_at=excluded.updated_at",
                (row["entity_id"], int(row.get("degree", 0)),
                 float(row.get("pagerank", 0.0)),
                 float(row.get("betweenness", 0.0)),
                 row.get("community_id"), row.get("run_id", ""),
                 row.get("updated_at", "")),
            )

    def get_analytics(self, entity_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM entity_analytics WHERE "
                               "entity_id = ?", (entity_id,)).fetchone()
        return dict(row) if row else None

    def list_analytics(self, community_id: int | None = None) -> list[dict]:
        with self._session() as conn:
            if community_id is None:
                rows = conn.execute("SELECT * FROM entity_analytics ORDER BY "
                                    "entity_id").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entity_analytics WHERE community_id = ? "
                    "ORDER BY entity_id", (community_id,)).fetchall()
        return [dict(r) for r in rows]

    def save_anomaly(self, anomaly: dict) -> None:
        """INSERT per scoring run (history preserved; readers take latest)."""
        with self._session() as conn:
            conn.execute(
                "INSERT INTO anomalies (id, entity_id, score, severity, "
                "reason, features, model_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (anomaly["id"], anomaly["entity_id"],
                 float(anomaly["score"]), anomaly["severity"],
                 anomaly["reason"], json.dumps(anomaly.get("features") or {}),
                 anomaly["model_version"], anomaly.get("created_at", "")),
            )

    def latest_anomaly(self, entity_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM anomalies WHERE entity_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (entity_id,)).fetchone()
        if row is None:
            return None
        anomaly = dict(row)
        anomaly["features"] = json.loads(anomaly["features"] or "{}")
        return anomaly

    def list_anomalies(self) -> list[dict]:
        """Latest anomaly row per entity (window function, portable)."""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT a.*, ROW_NUMBER() OVER ("
                "PARTITION BY entity_id ORDER BY created_at DESC, id DESC"
                ") AS rn FROM anomalies a) WHERE rn = 1 "
                "ORDER BY score DESC, entity_id").fetchall()
        anomalies = []
        for row in rows:
            anomaly = dict(row)
            anomaly["features"] = json.loads(anomaly["features"] or "{}")
            anomalies.append(anomaly)
        return anomalies

    def record_analytics_run(self, run: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO analytics_runs (id, created_at, node_count, "
                "edge_count, methods) VALUES (?, ?, ?, ?, ?)",
                (run["id"], run.get("created_at", ""),
                 int(run.get("node_count", 0)),
                 int(run.get("edge_count", 0)),
                 json.dumps(run.get("methods") or {})),
            )

    # -- users (Phase 6; mirrors DATABASE_SCHEMA.md §2) -------------------
    def create_user(self, user: dict) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, role, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user["id"], user["name"], user["email"].lower(),
                 user["password_hash"], user["role"],
                 user.get("created_at", ""), user.get("updated_at", "")),
            )

    def get_user_by_email(self, email: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?",
                               ((email or "").lower(),)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?",
                               (user_id,)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at, id"
                                ).fetchall()
        return [dict(row) for row in rows]

    def set_user_role(self, user_id: str, role: str) -> None:
        if role not in USER_ROLES:
            raise ValueError(f"unknown role: {role}")
        with self._session() as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?",
                         (role, user_id))
