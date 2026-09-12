# API_SPEC.md — Crime Network Intelligence System

> Contract between the FastAPI backend and React frontend.
> Base path: `/api`. This file is binding per `AGENTS.md` §6 and `PROJECT_SPEC.md` §21.
> Do not silently change request/response structures. Breaking changes require approval + spec update + test + implementation updates.
> All examples use synthetic data. Investigation Priority Score is a triage aid, never proof of criminality.

---

## 0. Conventions

- Base path: `/api` (no version prefix in URL for MVP; see §17 for versioning).
- Content type: `application/json` unless stated (`multipart/form-data` for uploads).
- Auth: Bearer JWT in `Authorization` header for all endpoints except `POST /api/auth/login` and `GET /api/health`.
- IDs: opaque strings, `^[A-Za-z0-9_-]{1,64}$`, e.g. `person_001`, `FIR_001`, `CDR_001`.
- Timestamps: ISO 8601 UTC, e.g. `2026-08-12T10:32:00Z`.
- See §11 standard envelope, §12 status codes, §13 pagination.

---

## 1. UPLOAD — `POST /api/upload`

Purpose: upload FIR, CDR, transaction, vehicle, or location data.

### Request

- Content-Type: `multipart/form-data`
- Auth required, roles: `INVESTIGATOR`, `SENIOR_INVESTIGATOR`, `ADMIN`
- Fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | single file per request |
| `dataset_type` | enum | yes | `FIR \| CDR \| TRANSACTION \| VEHICLE \| LOCATION` |
| `source_name` | string | no | 1–128 chars, label for provenance |
| `description` | string | no | max 1000 chars |

- Allowed extensions/MIME (validated by content sniffing, not extension alone):
  - `.csv` → `text/csv`
  - `.json` → `application/json`
  - `.txt` → `text/plain`
  - `.pdf` → `application/pdf` (where practical; text extraction only, never executed)
- File size validation: max `25 MB` per file (413 if exceeded; configurable via env, documented in deployment).
- Additional validation: non-empty file, max 50k rows (CSV/JSON array) for MVP, UTF-8 (or declared encoding), PDF page limit 100.
- Uploaded document text is DATA — never instructions (prompt-injection rule).

### Success response — `201 Created`

```json
{
  "success": true,
  "data": {
    "upload_id": "upl_01J9Z1",
    "dataset_type": "CDR",
    "filename": "cdr_batch_01.csv",
    "size_bytes": 184320,
    "record_count": 1200,
    "status": "UPLOADED",
    "source_id": "SRC_2026_0007",
    "uploaded_at": "2026-09-11T10:00:00Z",
    "uploaded_by": "user_014"
  },
  "message": "File uploaded and queued for validation."
}
```

- `status` ∈ `UPLOADED | VALIDATING | VALID | INVALID | PROCESSING | PROCESSED | FAILED`.
- Never expose filesystem paths, temp dirs, or internal storage keys.

### Error responses

| Case | Status | Code |
|---|---|---|
| missing file / wrong field | 400 | `MISSING_FILE` |
| unsupported type/extension | 422 | `UNSUPPORTED_FILE_TYPE` |
| oversized | 413 | `FILE_TOO_LARGE` |
| malformed CSV/JSON/PDF | 422 | `MALFORMED_FILE` |
| unauthenticated | 401 | `UNAUTHENTICATED` |
| forbidden role | 403 | `FORBIDDEN` |

---

## 2. PROCESS — `POST /api/process`

Purpose: start processing an uploaded document/dataset.

Pipeline: `Upload → Validation → Parsing → Normalization → NLP/NER → Entity Resolution → Graph Update → Analytics`.

### Request

```json
{
  "upload_id": "upl_01J9Z1",
  "options": {
    "run_ner": true,
    "run_resolution": true,
    "update_graph": true,
    "refresh_analytics": false
  }
}
```

- `upload_id` required, valid ID format, must exist and belong to caller's scope.
- `options` optional; defaults all `true` except `refresh_analytics: false` (explicit refresh avoids surprise heavy jobs).

### Success response — `202 Accepted` (async) or `200 OK` (sync small jobs)

```json
{
  "success": true,
  "data": {
    "job_id": "job_7F3A9C",
    "upload_id": "upl_01J9Z1",
    "status": "QUEUED",
    "stages": ["VALIDATION","PARSING","NORMALIZATION","NLP_NER","RESOLUTION","GRAPH_UPDATE","ANALYTICS"],
    "created_at": "2026-09-11T10:01:00Z"
  },
  "message": "Processing queued."
}
```

- `status` ∈ `QUEUED | RUNNING | SUCCEEDED | FAILED | PARTIAL`.
- Poll via `GET /api/process/{job_id}` (same envelope; includes per-stage status + error detail).
- The API must not claim success until persistence/processing succeeds. `SUCCEEDED` only after verified writes; otherwise `FAILED`/`PARTIAL` with stage errors. Never `200` + `success: true` on failed persistence.

### Error responses

| Case | Status | Code |
|---|---|---|
| unknown upload_id | 404 | `UPLOAD_NOT_FOUND` |
| already processing | 409 | `ALREADY_PROCESSING` |
| invalid options | 422 | `VALIDATION_ERROR` |
| downstream DB/graph failure | 500/503 | `PROCESSING_FAILED` / `SERVICE_UNAVAILABLE` |

---

## 3. ENTITIES

### 3.1 `GET /api/entities` — list/search entities

Supported types: `PERSON PHONE LOCATION VEHICLE ORGANIZATION DATE ACCOUNT`.

Query params:

| Param | Default | Max | Notes |
|---|---|---|---|
| `type` | — | — | single type filter, validated against enum |
| `q` | — | 128 chars | substring search on name/value (see §8) |
| `page` | 1 | — | ≥1 |
| `page_size` | 20 | 100 | clamp |
| `sort` | `name` | — | `name \| created_at \| priority` |
| `order` | `asc` | — | `asc \| desc` |

Response `200`:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "person_001",
        "type": "PERSON",
        "name": "Rahul Sharma",
        "aliases": ["R. Sharma"],
        "source_refs": [{"document_id": "FIR_001", "record_id": "FIR_001_R3"}],
        "confidence": 0.92,
        "priority_score": 0.81
      }
    ],
    "pagination": {"page": 1, "page_size": 20, "total": 1, "total_pages": 1}
  },
  "message": "Entities retrieved."
}
```

Minimize PII: return only fields needed for listing; full detail only on `GET by id` with authz.

### 3.2 `GET /api/entities/{id}` — detail

Response `200`:

```json
{
  "success": true,
  "data": {
    "id": "person_001",
    "type": "PERSON",
    "name": "Rahul Sharma",
    "aliases": ["R. Sharma"],
    "source_refs": [
      {"document_id": "FIR_001", "record_id": "FIR_001_R3", "offsets": [120, 132], "confidence": 0.92}
    ],
    "attributes": {"phones": ["phone_011"], "accounts": ["acct_201"]},
    "analytics_summary": {"pagerank": 0.82, "betweenness": 0.77, "community_id": "C03", "anomaly_score": 0.91, "priority_score": 0.83},
    "related": [{"id": "phone_011", "type": "PHONE", "relation": "USED"}]
  },
  "message": "Entity retrieved."
}
```

- `404 NOT_FOUND` for unknown id; `400 INVALID_ID` for malformed id.
- Do not expose unnecessary sensitive information (no raw addresses, full account numbers, secrets).

---

## 4. GRAPH

### 4.1 `GET /api/graph/{id}` — Cytoscape.js graph

Query: `?depth=1&limit_nodes=100&limit_edges=300` (defaults; see §13).

Response `200` — exact Cytoscape-compatible shape:

```json
{
  "success": true,
  "data": {
    "nodes": [{"id": "P001", "label": "Rahul Sharma", "type": "PERSON"}],
    "edges": [{"id": "R001", "source": "P001", "target": "P002", "type": "CALLED"}]
  },
  "message": "Graph retrieved."
}
```

Optional edge metadata (when available, never breaking the base shape):

```json
{"id": "R001", "source": "P001", "target": "P002", "type": "CALLED",
 "metadata": {"confidence": 0.88, "timestamp": "2026-08-12T10:32:00Z", "source_record": "CDR_001"}}
```

Node `type` ∈ entity types (§3); edge `type` ∈ `CALLED MET LOCATED_AT OWNS USED TRANSFERRED_TO ASSOCIATED_WITH MENTIONED_IN WORKS_FOR TRAVELLED_TO`.

### 4.2 `GET /api/graph/{id}/neighbors`

Query params:

| Param | Default | Max | Notes |
|---|---|---|---|
| `depth` | 1 | 3 | traversal depth cap |
| `rel_types` | — | 10 types | comma list, validated |
| `node_types` | — | 7 types | comma list, validated |
| `limit_nodes` | 100 | 500 | clamp |
| `limit_edges` | 300 | 1500 | clamp |

Reasonable limits enforced to prevent unbounded traversal; `429` + `Retry-After` if abused. Response shape identical to §4.1 plus `pagination`-style `truncated: true/false`.

---

## 5. ANALYTICS

- `GET /api/analytics/pagerank?entity_id=&page=&page_size=`
- `GET /api/analytics/betweenness?entity_id=&page=&page_size=`
- `GET /api/analytics/communities?community_id=&page=&page_size=`

Response `200`:

```json
{
  "success": true,
  "data": {
    "items": [
      {"entity_id": "person_001", "pagerank": 0.82, "betweenness": 0.77, "community_id": "C03"}
    ],
    "pagination": {"page": 1, "page_size": 20, "total": 150, "total_pages": 8}
  },
  "message": "Analytics retrieved."
}
```

- Single-entity query (`?entity_id=`) returns one object or `404`.
- Metrics are analytical signals. Never label as proof of criminal activity; include `disclaimer` field in UI-facing payloads: `"Analytical signal only — not evidence of guilt."`

---

## 6. ANOMALIES — `GET /api/anomalies`

Query: `?entity_id=&severity=&min_score=&page=&page_size=` (`severity` ∈ `LOW|MEDIUM|HIGH`, `min_score` 0–1).

Response `200`:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "entity_id": "person_001",
        "features": {
          "calls_per_day": 67,
          "unique_contacts": 24,
          "average_call_duration": 320,
          "night_calls": 12,
          "transaction_count": 14,
          "transaction_amount": 850000,
          "unique_locations": 9,
          "location_changes": 7
        },
        "anomaly_score": 0.91,
        "severity": "HIGH",
        "reasons": ["Communication spike", "Unusual transaction activity", "Unusual location pattern"]
      }
    ],
    "pagination": {"page": 1, "page_size": 20, "total": 12, "total_pages": 1}
  },
  "message": "Anomalies retrieved."
}
```

- Severity mapping (fixed): `≥0.8 HIGH, ≥0.5 MEDIUM, else LOW`.
- Filtering, pagination per §13; errors per §11–§12.

---

## 7. TIMELINE — `GET /api/timeline/{id}`

Query: `?from=&to=&types=&page=&page_size=` (`types` subset of event types; `from/to` ISO 8601).

Response `200`:

```json
{
  "success": true,
  "data": {
    "entity_id": "person_001",
    "events": [
      {"timestamp": "2026-08-12T10:32:00Z", "type": "CALL", "description": "Rahul called Amit", "source_id": "CDR_001"}
    ],
    "pagination": {"page": 1, "page_size": 50, "total": 1, "total_pages": 1}
  },
  "message": "Timeline retrieved."
}
```

Event `type` ∈ `CALL MEETING TRANSACTION LOCATION TRAVEL FIR VEHICLE`. Chronological ascending; source refs preserved (`source_id` required on every event).

---

## 8. SEARCH — `GET /api/search?q={query}`

- `q` required, 2–128 chars, trimmed; `400` if missing/too short; `422` if illegal control chars.
- Searches entity name/value + aliases only (no full-document grep in MVP).
- Matching: case-insensitive substring; no regex from client; special chars escaped server-side.
- Pagination: `page`/`page_size` per §13.
- Injection prevention: parameterized ORM/Cypher, length caps, no raw query passthrough.

Response `200`:

```json
{
  "success": true,
  "data": {
    "items": [{"id": "person_001", "type": "PERSON", "name": "Rahul Sharma", "match": "name"}],
    "pagination": {"page": 1, "page_size": 20, "total": 1, "total_pages": 1}
  },
  "message": "Search complete."
}
```

---

## 9. INVESTIGATION — `GET /api/investigation/{id}`

Response `200`:

```json
{
  "success": true,
  "data": {
    "entity": {"id": "person_001", "type": "PERSON", "name": "Rahul Sharma"},
    "priority": {
      "score": 0.83,
      "formula": "0.35 × PageRank + 0.35 × Betweenness + 0.30 × Anomaly Score",
      "formula_version": "v1",
      "components": {"pagerank": 0.82, "betweenness": 0.77, "anomaly_score": 0.91},
      "disclaimer": "Investigation-priority indicator only. Not probability of criminality, guilt, proof of criminal activity, or future-crime prediction."
    },
    "graph_metrics": {"pagerank": 0.82, "betweenness": 0.77, "community_id": "C03"},
    "anomaly": {"anomaly_score": 0.91, "severity": "HIGH", "reasons": ["Communication spike"]},
    "explanations": ["High network centrality", "High betweenness / bridge position", "Unusual transaction activity"],
    "timeline_ref": "/api/timeline/person_001",
    "key_relationships": [{"id": "R001", "source": "person_001", "target": "person_002", "type": "CALLED"}],
    "sources": [{"document_id": "FIR_001", "record_id": "FIR_001_R3"}]
  },
  "message": "Investigation summary retrieved."
}
```

Formula fixed per `PROJECT_SPEC.md` §9. The four forbidden framings must never appear in responses, UI copy, or docs.

---

## 10. AUTHENTICATION

- Mechanism: JWT Bearer (`Authorization: Bearer <token>`), short-lived access tokens + refresh rotation; passwords hashed with argon2/bcrypt server-side; secrets in env only.
- `POST /api/auth/login` `{username, password}` → `200 {access_token, token_type: "Bearer", expires_in}`; `401 INVALID_CREDENTIALS` (generic, no user-enumeration).
- `POST /api/auth/refresh`, `POST /api/auth/logout` (token revocation).
- Roles: `INVESTIGATOR | SENIOR_INVESTIGATOR | ADMIN`.

| Capability | INVESTIGATOR | SENIOR_INVESTIGATOR | ADMIN |
|---|---|---|---|
| upload/process | ✓ | ✓ | ✓ |
| read entities/graph/timeline/search/anomalies | ✓ | ✓ | ✓ |
| investigation report | ✓ | ✓ | ✓ |
| trigger analytics refresh | — | ✓ | ✓ |
| user management | — | — | ✓ |

- All endpoints protected except `POST /api/auth/login`, `GET /api/health`. Authz enforced server-side on every request; frontend roles are display-only.
- Auth errors: `401 UNAUTHENTICATED` (missing/expired token), `403 FORBIDDEN` (valid token, insufficient role). No redirect-to-login for API; JSON envelope always.

---

## 11. STANDARD RESPONSE FORMAT

Success (2xx):

```json
{"success": true, "data": {}, "message": "..."}
```

Error (4xx/5xx):

```json
{"success": false, "error": {"code": "...", "message": "..."}}
```

- `message` human-readable, no internals. Never expose stack traces, SQL/Cypher queries, filesystem paths, credentials, or internal secrets.
- Validation errors include `error.details[]` with `{field, issue}` only (no schema dumps).

---

## 12. HTTP STATUS CODES

| Code | Use |
|---|---|
| 200 | successful read / sync action |
| 201 | upload created, resource created |
| 202 | processing/analytics job accepted (async) |
| 400 | malformed request (bad ID format, missing required param) |
| 401 | missing/invalid/expired auth |
| 403 | authenticated but forbidden for role/resource |
| 404 | upload/entity/job/graph node not found |
| 409 | conflict (already processing, duplicate upload hash) |
| 413 | file/payload too large |
| 422 | semantically invalid (unsupported file type, malformed CSV/JSON, bad enum/range) |
| 429 | rate limited (with `Retry-After`) |
| 500 | unexpected server failure (generic message, logged with correlation id) |
| 503 | downstream unavailable (PostgreSQL/Neo4j/NLP worker) |

Do not use codes arbitrarily; validation → 400/422, auth → 401/403, capacity → 413/429.

---

## 13. PAGINATION & LIMITS

Envelope: `{"page", "page_size", "total", "total_pages"}`. `page ≥ 1`; `page_size` clamped to max.

| Resource | Default page_size | Max |
|---|---|---|
| entity lists | 20 | 100 |
| graph neighbors (nodes/edges) | 100 / 300 | 500 / 1500 |
| search | 20 | 50 |
| anomaly results | 20 | 100 |
| timeline | 50 | 200 |

No unbounded responses. `depth` for graph traversal max 3. Oversized `page_size` clamped, not rejected.

---

## 14. VALIDATION

All inputs validated (Pydantic v2 / FastAPI `Query`/`Path`/`File`):

- IDs: pattern `^[A-Za-z0-9_-]{1,64}$`; unknown → 404, malformed → 400.
- Query params/pagination/filters: ranges, enums, length caps; invalid → 422.
- File uploads: type sniffing, size, row/page caps, encoding (§1).
- Bodies: strict schemas, `extra="forbid"`; timestamps ISO 8601; numerics range-checked (scores 0–1, amounts ≥0).
- Fail closed: reject on first violation class; return structured `details[]`.

---

## 15. SECURITY

- Authentication + server-side authorization on every endpoint (§10).
- Input validation everywhere (§14); output encoding for UI strings.
- Rate limiting on `POST /api/upload`, `POST /api/process`, `GET /api/search`, `GET /api/graph/**` (e.g., 30/min/IP + per-user quotas; `429` on exceed).
- CORS: allowlist specific frontend origins only; no `*` with credentials; restrict methods/headers.
- Secure errors: generic messages + correlation id; full detail server-side logs only, no sensitive info in logs.
- File upload: sandboxed storage, random object names, no path passthrough, AV/size/type checks, PDF text-extraction sandbox (§1).
- SQL/Cypher injection: parameterized queries/ORM only; never interpolate user input; **never accept raw Cypher or raw SQL from the frontend** — `400/422` if such fields detected.
- Path traversal: reject `..`, absolute paths, null bytes, symlink escapes.
- Logging: no passwords, tokens, PII beyond minimum, file paths, or query internals.

---

## 16. DATA PROVENANCE

Where applicable preserve: `source_id`, `document_id`, `record_id`, `timestamp`, `confidence`, `processing status` (upload job + stage).

- Entity, graph edge metadata, timeline events, anomaly items, investigation sources must carry provenance.
- Never silently drop provenance from analytical results; if unknown, return `null` + `provenance_status: "missing"` rather than omitting the key.

---

## 17. API VERSIONING

- MVP: unversioned `/api` with `formula_version` and contract fields versioned in payloads.
- Forward path (no frontend break): introduce `/api/v2` alongside `/api` (aliased to v1), deprecate with `Sunset` + `Deprecation` headers and 6-month overlap. Additive fields anytime; renames/removals only in a new major version.
- No premature `/v1` prefix complexity for MVP.

---

## 18. FRONTEND CONTRACT

Pages → endpoints:

| Page | Endpoints |
|---|---|
| Dashboard (Overview) | `GET /api/entities?page_size=5&sort=priority`, `GET /api/anomalies?severity=HIGH`, `GET /api/health` |
| NetworkExplorer | `GET /api/graph/{id}`, `GET /api/graph/{id}/neighbors`, `GET /api/search` |
| EntityProfile | `GET /api/entities/{id}`, `GET /api/graph/{id}/neighbors?depth=1`, `GET /api/timeline/{id}?page_size=5` |
| Anomalies | `GET /api/anomalies`, `GET /api/analytics/*` |
| Investigation | `GET /api/investigation/{id}`, `GET /api/timeline/{id}` |

Components:

- `NetworkGraph` ← §4 payload (`nodes`/`edges` + optional `metadata`).
- `EntityCard` ← `GET /api/entities/{id}` (summary fields).
- `SearchBar` ← `GET /api/search?q=` (debounced, min 2 chars).
- `Timeline` ← `GET /api/timeline/{id}` events.
- `AnomalyCard` ← `GET /api/anomalies` items.
- `StatsCard` ← analytics/priority aggregates.

Frontend must use only documented contracts; **no direct PostgreSQL or Neo4j access** from React. Auth token stored in memory (not localStorage for XSS safety); roles from `/api/auth/me` for display only.

---

## 19. API TESTING

Required test matrix (backend + contract tests):

- successful requests (each endpoint, golden payload shape)
- invalid requests (bad enum, bad ID format → 400/422)
- missing authentication (→ 401, no token / malformed Bearer)
- unauthorized roles (INVESTIGATOR hitting admin-only → 403)
- nonexistent entities/uploads/jobs (→ 404)
- invalid IDs (path traversal, overlong → 400)
- malformed uploads (bad CSV/JSON/PDF → 422)
- oversized uploads (→ 413)
- empty payloads (→ 400/422)
- database failures (PostgreSQL down → 503, no false success)
- processing failures (NLP/graph stage fail → job FAILED, no `success: true`)
- pagination limits (clamp, max enforcement, no unbounded)
- injection attempts (SQL/Cypher fragments in `q`, `id`, filters → rejected/escaped, no query echo)

---

## 20. CONTRACT CHANGE POLICY

`API_SPEC.md` is a contract. Breaking change requires:

1. Identify the affected endpoint.
2. Explain why the change is needed.
3. Identify frontend/backend impact.
4. Update `API_SPEC.md`.
5. Update affected tests.
6. Update affected implementation.

Never silently change an API contract. Prefer additive changes (new optional fields/endpoints) over breaking ones.
