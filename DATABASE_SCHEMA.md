# DATABASE_SCHEMA.md — Crime Network Intelligence System (PostgreSQL)

> Authoritative specification for the PostgreSQL database. Binding contract per `AGENTS.md` §6 and `PROJECT_SPEC.md` §21.
> PostgreSQL stores structured application data and metadata. Neo4j stores the knowledge graph. Do not duplicate graph functionality in PostgreSQL.
> All examples use synthetic data. Anomaly/priority scores are analytical signals, never probability of criminality.

---

## 1. DATABASE RESPONSIBILITY

PostgreSQL is responsible for structured application data and metadata:

- Users
- Documents
- Entities
- Entity Mentions
- Investigations
- Anomalies
- Audit Logs

Neo4j is responsible for the knowledge graph and graph relationships (nodes per `PROJECT_SPEC.md` §6, relationships per §5, served via `API_SPEC.md` §4).

Rules:

- Do not duplicate graph traversal, centrality storage as source of truth, or relationship topology in PostgreSQL. PostgreSQL may cache score summaries (e.g., `ANOMALIES.score`) for API reads, but Neo4j remains the graph source of truth.
- Every row that derives from an upload must be traceable to its source document (see §11).
- Raw evidence immutable; derived data separate (see §11).

Conventions (apply to all tables):

- Primary keys: `TEXT` opaque IDs (`^[A-Za-z0-9_-]{1,64}$`), e.g. `user_014`, `FIR_001`, `person_001`. No sequential IDs exposed via API.
- Timestamps: `TIMESTAMPTZ`, stored in UTC, ISO 8601 at API boundary (`2026-08-12T10:32:00Z`). `created_at` set once, never updated; `updated_at` via trigger/application on update.
- All tables have `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- Use `TEXT` (not `VARCHAR(n)`) with `CHECK (char_length(col) ...)` where length limits are needed, so limits are explicit and testable.

---

## 2. USERS

Table: `users`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY, CHECK id pattern | e.g. `user_014` |
| `name` | TEXT | NOT NULL, CHECK (1–128 chars) | display name, synthetic |
| `email` | CITEXT or TEXT | NOT NULL, UNIQUE, CHECK email format | unique login; normalize lowercase on write |
| `password_hash` | TEXT | NOT NULL | argon2id/bcrypt hash only; never plaintext; never returned by API |
| `role` | TEXT | NOT NULL, CHECK role enum | `INVESTIGATOR \| SENIOR_INVESTIGATOR \| ADMIN` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | bump on update |

Requirements:

- `email` unique (case-insensitive; use `CITEXT` or unique lower index). Duplicate → reject (`409` at API).
- `role` validated by `CHECK (role IN (...))`; invalid → reject.
- `password_hash` holds a secure hash only. Credentials never appear in API responses, logs, or audit metadata.
- Timestamps consistent (UTC, `TIMESTAMPTZ`).

Keys/indexes:

- PK: `users(id)`.
- UNIQUE: `users(email)` (case-insensitive).
- INDEX: `users(role)` only if role-filtered admin listing is required (justify before adding; see §14).

---

## 3. DOCUMENTS

Table: `documents`. One row per uploaded file (`API_SPEC.md` §1).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | e.g. `DOC_2026_0007` / `upl_01J9Z1` mapped to stable doc id |
| `type` | TEXT | NOT NULL, CHECK enum | `FIR \| CDR \| TRANSACTION \| VEHICLE \| LOCATION` |
| `filename` | TEXT | NOT NULL, CHECK (1–255 chars) | original client filename for display only; never trusted as path |
| `source` | TEXT | NULL, CHECK (1–128 chars) | `source_name` label for provenance |
| `uploaded_by` | TEXT | NOT NULL, FK → `users(id)` | actor; see §9–§10 |
| `uploaded_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable |
| `status` | TEXT | NOT NULL DEFAULT 'UPLOADED', CHECK enum | `UPLOADED \| VALIDATING \| PROCESSING \| PROCESSED \| FAILED` |
| `file_hash` | TEXT | NOT NULL, CHECK SHA-256 hex (64 chars) | `SHA-256(file_bytes)`; integrity verification + dedupe |
| `metadata` | JSONB | NOT NULL DEFAULT '{}' | size_bytes, record_count, mime, encoding, page/row counts; no secrets/paths |

Document types: `FIR, CDR, TRANSACTION, VEHICLE, LOCATION` (match `dataset_type`).
Statuses: `UPLOADED, VALIDATING, PROCESSING, PROCESSED, FAILED` (processing lifecycle; `API_SPEC.md` §1–§2).

Requirements:

- Preserve original source info (`filename`, `source`, `file_hash`, `uploaded_by/at`, `metadata`). Never silently overwrite.
- `uploaded_by` FK → `users(id)` with `ON DELETE RESTRICT` (protect provenance).
- `file_hash` SHA-256 hex supports integrity verification and duplicate detection (duplicate hash → `409` candidate, not silent overwrite).
- Raw evidence immutable: status/metadata may advance; file bytes + `file_hash` never mutated. Corrections create new document rows.
- `filename` display-only; storage uses random object names outside DB; no path construction from filename.

---

## 4. ENTITIES

Table: `entities`. Canonical resolved entities (`PROJECT_SPEC.md` §4).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | stable canonical ID, e.g. `person_001` |
| `type` | TEXT | NOT NULL, CHECK enum | `PERSON \| PHONE \| LOCATION \| VEHICLE \| ORGANIZATION \| DATE \| ACCOUNT` |
| `canonical_name` | TEXT | NOT NULL, CHECK (1–256 chars) | display value |
| `normalized_name` | TEXT | NOT NULL, CHECK (1–256 chars) | normalized for dedupe/search (lower, trimmed, canonical spacing) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | bump on merge/rename |

Requirements:

- Stable canonical ID: never reused, never changed after creation. Merges mark superseded rows (or a merge-link table in a later migration) — never delete source rows silently; see §11.
- Valid entity type enforced by CHECK.
- Normalized values where appropriate (`normalized_name` deterministic function of type + value; `DATE` ISO 8601).
- No accidental duplicate canonical IDs: PK + application-level `(type, normalized_name)` dedupe check before insert (unique index optional — only if resolution policy guarantees it; otherwise enforce in service with provenance review, not silent upsert).

---

## 5. ENTITY MENTIONS

Table: `entity_mentions`. Links canonical entity ↔ original source mention.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | e.g. `men_000123` |
| `entity_id` | TEXT | NOT NULL, FK → `entities(id)` | canonical target |
| `document_id` | TEXT | NOT NULL, FK → `documents(id)` | source document |
| `text` | TEXT | NOT NULL, CHECK (1–1000 chars) | original mention text verbatim |
| `confidence` | DOUBLE PRECISION | NULL, CHECK (0–1) | NER/extraction confidence where available |
| `extraction_method` | TEXT | NULL, CHECK (1–64 chars) | e.g. `spacy_ner_v1`, `regex_phone_v1`, `manual_v1` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable |

Purpose: preserve provenance — which document span produced which canonical entity, with what confidence and method.

Requirements:

- Preserve source provenance (`document_id`), original mention `text`, `confidence`, `extraction_method`.
- Do not replace mentions with only the canonical value; `text` stays verbatim.
- FKs: `entity_id → entities(id)`, `document_id → documents(id)`, both `ON DELETE RESTRICT` (see §10).

---

## 6. INVESTIGATIONS

Table: `investigations`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | e.g. `inv_0007` |
| `name` | TEXT | NOT NULL, CHECK (1–200 chars) | case title, synthetic |
| `primary_entity_id` | TEXT | NOT NULL, FK → `entities(id)` | focus entity |
| `created_by` | TEXT | NOT NULL, FK → `users(id)` | owner |
| `status` | TEXT | NOT NULL DEFAULT 'OPEN', CHECK enum | `OPEN \| ACTIVE \| CLOSED \| ARCHIVED` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | bump on status/name change |

Statuses: `OPEN, ACTIVE, CLOSED, ARCHIVED` (forward-only in app logic; reopen creates audit entry, not silent revert).

Relationships: `primary_entity_id → entities(id)`, `created_by → users(id)`, both `ON DELETE RESTRICT`.

Indexes: `investigations(primary_entity_id)`, `investigations(created_by)`, `investigations(status)` (see §14).

---

## 7. ANOMALIES

Table: `anomalies`. Persisted Isolation Forest results (`API_SPEC.md` §6).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | e.g. `anom_00031` |
| `entity_id` | TEXT | NOT NULL, FK → `entities(id)` | scored entity |
| `score` | DOUBLE PRECISION | NOT NULL, CHECK (0–1) | normalized anomaly score |
| `severity` | TEXT | NOT NULL, CHECK enum | `LOW \| MEDIUM \| HIGH` (`≥0.8 HIGH, ≥0.5 MEDIUM, else LOW`) |
| `reason` | TEXT | NOT NULL, CHECK (1–1000 chars) | human-readable reasons joined/summarized |
| `features` | JSONB | NOT NULL | the 8 fixed features: calls_per_day, unique_contacts, average_call_duration, night_calls, transaction_count, transaction_amount, unique_locations, location_changes |
| `model_version` | TEXT | NOT NULL, CHECK (1–64 chars) | e.g. `iforest_v1.2` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable scoring run timestamp |

Requirements:

- `score` numeric bounded `[0, 1]` per app convention (CHECK enforced).
- Preserve `model_version` (model + feature-window version) and explanation (`reason` + `features`).
- Never describe score as probability of criminality in stored copy, API, or UI. Column named `score`, not `criminality`.

---

## 8. AUDIT LOGS

Table: `audit_logs`. Append-oriented tamper-evident record.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT PK | PRIMARY KEY | e.g. `aud_000001` (or ULID); insertion order ≠ trust order — `previous_hash` is the chain |
| `user_id` | TEXT | NULL, FK → `users(id)` | actor; NULL only for system jobs (must set `metadata.actor: "system"`) |
| `action` | TEXT | NOT NULL, CHECK (1–64 chars) | e.g. `UPLOAD, PROCESS, RESOLVE, GRAPH_UPDATE, SCORE, LOGIN` |
| `resource_type` | TEXT | NOT NULL, CHECK (1–64 chars) | e.g. `DOCUMENT, ENTITY, INVESTIGATION, ANOMALY` |
| `resource_id` | TEXT | NULL, CHECK (1–64 chars) | target id where applicable |
| `timestamp` | TIMESTAMPTZ | NOT NULL DEFAULT now() | immutable event time |
| `metadata` | JSONB | NOT NULL DEFAULT '{}' | actor, input/output hashes, stage, job id; never passwords/tokens/secrets |
| `hash` | TEXT | NOT NULL, UNIQUE, CHECK SHA-256 hex | `SHA256(prev_hash || canonical(record))` |
| `previous_hash` | TEXT | NOT NULL | hash of previous row (`GENESIS` sentinel for first row) |

Hash chaining (practical, where applicable):

```text
current_hash = SHA256(previous_hash + canonicalized_record)
```

`canonicalized_record` = deterministic JSON of `(user_id, action, resource_type, resource_id, timestamp, metadata)` with sorted keys, UTF-8.

Requirements:

- Append-oriented: application role has INSERT + SELECT only; no UPDATE/DELETE for ordinary users (enforced via GRANTs + CHECK policy; see §12). Corrections are new compensating rows.
- `previous_hash` references previous row's `hash`; verifier recomputes chain in `timestamp, id` order.
- Never store passwords, tokens, or secrets in `metadata`.
- Tamper-evident mechanism only — not a decentralized blockchain; never claim otherwise.

---

## 9. RELATIONSHIPS

Foreign-key map (all `ON DELETE RESTRICT` unless §10 justifies otherwise):

```text
users
  ↓ documents.uploaded_by        (documents.uploaded_by → users.id)

documents
  ↓ entity_mentions.document_id  (entity_mentions.document_id → documents.id)

entities
  ↓ entity_mentions.entity_id    (entity_mentions.entity_id → entities.id)

entities
  ↓ investigations.primary_entity_id (investigations.primary_entity_id → entities.id)

users
  ↓ investigations.created_by    (investigations.created_by → users.id)

entities
  ↓ anomalies.entity_id          (anomalies.entity_id → entities.id)

users
  ↓ audit_logs.user_id           (audit_logs.user_id → users.id, nullable for system)
```

Referential notes:

- `documents → users`, `investigations → users/entities`, `mentions/anomalies → parents` all RESTRICT to protect evidence/provenance.
- `audit_logs.previous_hash` is a logical chain link, not a SQL FK (hash-addressed, verified in code/tests).

---

## 10. DATA INTEGRITY

- Primary keys: all tables `id TEXT PRIMARY KEY` with application-validated pattern.
- Foreign keys: §9 list; `NOT NULL` except `audit_logs.user_id`, `audit_logs.resource_id`; all `ON DELETE RESTRICT`. No `ON DELETE CASCADE` on evidence/provenance (`documents`, `entity_mentions`, `audit_logs`, `entities` referenced by mentions/anomalies/investigations) unless explicitly justified + spec-updated.
- NOT NULL: all columns except `documents.source`, `entity_mentions.confidence/extraction_method`, `audit_logs.user_id/resource_id`.
- UNIQUE: `users(email)` (case-insensitive), `audit_logs(hash)`. `documents(file_hash)` non-unique index (dedupe signal, still allows re-upload with new row).
- CHECK: role/type/status/severity enums; score/confidence ranges; SHA-256 hex patterns; length bounds; `features` contains the 8 required keys (application + test enforced; DB `CHECK (features ?& array[...])` where PG version supports it).
- Indexes: §14 list; FK columns indexed.
- Cascading: default RESTRICT. Destructive cascades forbidden for evidence/provenance. Deleting a user/document/entity with dependents → reject; anonymize/retire via status, not delete.

---

## 11. IMMUTABILITY & PROVENANCE

Required chain support:

```text
RAW SOURCE → DOCUMENT → ENTITY MENTION → CANONICAL ENTITY
```

- `RAW SOURCE` (file bytes, `file_hash`) → `documents` row (immutable).
- `documents` → `entity_mentions` rows (verbatim `text` + `confidence` + `extraction_method`).
- `entity_mentions` → `entities` canonical row (`normalized_name`, stable id).
- Normalization/resolution write new rows/columns on derived copies only; never mutate raw bytes, `file_hash`, or mention `text`.
- Entity merge: keep all original `entity_mentions` + source refs; superseded canonical rows retained (status/merge-link via future migration, not delete). Never permanently erase resolution evidence.
- Downstream (`anomalies`, `investigations`) reference canonical ids + carry `model_version`/`source refs` so any score is traceable to documents.

---

## 12. SECURITY

- Credentials via environment variables/secrets manager only; never in source, migrations, logs, API, or audit `metadata`.
- Least-privilege DB users: `app_rw` (CRUD, no DDL, no audit UPDATE/DELETE), `app_ro` (SELECT for reporting), `migrator` (DDL via migrations only). `audit_logs` INSERT+SELECT for `app_rw`; REVOKE UPDATE/DELETE.
- No DB credentials in source code or committed config.
- Parameterized SQL / ORM bindings only; never concatenate user input into SQL. No raw SQL accepted from frontend (reject `400/422`).
- Restricted network exposure: PostgreSQL not publicly exposed; Docker-internal network + authenticated connections; TLS where deployed beyond localhost.
- Safe connection config: parameterized connection strings from env, statement timeouts, least-privilege per service.
- Connection pooling (e.g., PgBouncer/SQLAlchemy pool) with bounded size; no unbounded connections per request.
- Sensitive fields excluded from API responses: `password_hash` never selected for API; audit `metadata` scrubbed; error messages generic (no SQL echo).

---

## 13. MIGRATIONS

- All schema changes via versioned migrations (e.g., Alembic), one migration per change set, ordered and idempotent-up.
- Never manually modify production schemas without a migration.
- Every change: versioned filename, reviewable diff, reversible (`downgrade`) where practical, tested up+down on a copy.
- Never silently change schema definitions — update this spec first (§18), then migration, then tests.

---

## 14. INDEXING

Justified indexes (query → index):

- `users(email)` UNIQUE — login lookup.
- `documents(type)` — dataset-type filtering.
- `documents(status)` — processing queue scans.
- `documents(uploaded_by)` — per-user document lists (FK).
- `documents(file_hash)` — dedupe/integrity checks.
- `entities(type)` — type filtering.
- `entities(normalized_name)` — dedupe/search.
- `entity_mentions(entity_id)` — mentions per entity (FK).
- `entity_mentions(document_id)` — mentions per document (FK).
- `investigations(primary_entity_id)` — investigations per entity (FK).
- `investigations(created_by)` + `investigations(status)` — owner/status queues.
- `anomalies(entity_id)` — anomalies per entity (FK).
- `anomalies(severity)` (+ `score DESC` composite where supported) — severity dashboards.
- `audit_logs(user_id)` — actor history.
- `audit_logs(timestamp DESC)` — chronological audit scans/verification.
- `audit_logs(resource_type, resource_id)` — resource history.

Add indexes only with query justification; measure before adding composite/GIN (`metadata`/`features` GIN only when filtering on them is proven).

---

## 15. TRANSACTION INTEGRITY

Use database transactions (atomic, verified commit) for multi-record writes:

- document processing: `documents` status advance + derived records + `audit_logs` entry.
- entity creation + mention creation: `entities` + `entity_mentions` rows together.
- investigation creation: `investigations` + audit entry.
- anomaly persistence: `anomalies` batch + audit entry.
- audit log creation: always in the same transaction as the action it records where feasible (action commit ⇒ audit commit).

Never report successful persistence when a transaction failed or rolled back. API `success: true` only after commit verified; on rollback return `500/503` with stage error, no partial-success claims.

---

## 16. BACKUP & RECOVERY

Development/production expectations (do not claim unless implemented):

- Nightly `pg_dump`/base backups + WAL archiving for prod; local Compose volume snapshots acceptable for dev only.
- Restore tested on a schedule (documented runbook + last-tested date); untested backups treated as absent.
- Migrations run before app start, backward-compatible where possible; failed migration blocks deploy, never half-applies (transactional DDL).
- Recovery: point-in-time restore procedure documented; evidence/audit tables restored together to preserve chain continuity; any gap disclosed in audit log as compensating entry post-restore.

---

## 17. TESTING

Required database tests:

- valid inserts for each table (happy path with FKs satisfied).
- invalid entity types rejected (CHECK).
- duplicate emails rejected (UNIQUE, case-insensitive).
- foreign-key violations rejected (mention/investigation/anomaly with bad parent).
- invalid roles rejected (CHECK).
- invalid anomaly severity rejected; out-of-range score rejected.
- document provenance preserved (mention → document → uploader chain intact).
- audit hash chaining verified (recompute chain; tampered row detected).
- transaction rollback (multi-row failure leaves no partial rows; API reports failure).
- authorization-related data access (service layer denies cross-owner reads where policy requires; `password_hash` never leaked in query results used by API).

---

## 18. SCHEMA CHANGE POLICY

`DATABASE_SCHEMA.md` is an architectural contract. If implementation requires a schema change:

1. Identify the change.
2. Explain why it is necessary.
3. Identify affected APIs/services.
4. Update this specification.
5. Create/update migration.
6. Update tests.

Never silently change the database schema. Prefer additive, backward-compatible changes (new nullable columns/tables) over breaking ones.
