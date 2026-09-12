# Crime Network Intelligence System

Investigation-support platform that processes **synthetic** FIR, CDR,
transaction, vehicle and location data, extracts entities and relationships,
builds a Neo4j knowledge graph, runs graph analytics and anomaly detection,
and exposes explainable intelligence through a React dashboard.

> Implemented stages: scaffolding + Phase 1 synthetic data + Phase 2
> ingestion/preprocessing + Phase 3 NLP extraction/entity resolution +
> Phase 4 Neo4j knowledge graph + Phase 5 analytics, anomaly detection
> and priority scoring + Phase 6 JWT auth/RBAC, timeline, search and the
> React dashboard. Complete application.

## Contract documents (binding — read before changing anything)

| File | Authority |
|---|---|
| `AGENTS.md` | Persistent development rules (auto-loaded) |
| `PROJECT_SPEC.md` | Scope, pipeline, entities, phases, contracts |
| `API_SPEC.md` | FastAPI ↔ React contract (`/api`) |
| `DATABASE_SCHEMA.md` | PostgreSQL contract |
| `NEO4J_SCHEMA.md` | Knowledge-graph contract |

## Repository layout

```text
data/            synthetic datasets (raw/processed/sample)
backend/         FastAPI app (GET /health only for now) + tests/
frontend/        React app (placeholder page) — src/components, pages, services/
scripts/         helper scripts (Phase 1 data generator)
docker-compose.yml  postgres + neo4j + backend + frontend
.env.example     placeholder env vars (copy to .env locally, never commit)
```

## Synthetic dataset (Phase 1)

Generate the deterministic demo dataset (stdlib only, no installs):

```bash
python scripts/generate_data.py [--seed 42] [--out-dir data/sample]
```

Files written to `data/sample/`:

| File | Records | Contents |
|---|---|---|
| `entities.csv` | 20 | canonical persons, aliases, phones, accounts, group, test pattern |
| `fir.csv` | 25 | FIR narratives with alias/format variants, all tagged `[SYNTHETIC RECORD]` |
| `cdr.csv` | 80 | caller, receiver, timestamp, duration |
| `transactions.csv` | 45 | sender/receiver accounts, amount (INR), timestamp |
| `vehicles.csv` | 16 | registration, owner (canonical or alias), source |
| `locations.csv` | 16 | name, lat/long (2 rows intentionally without coordinates) |
| `manifest.json` | — | seed, counts, pattern roles, synthetic disclaimer |

Patterns (analytics test fixtures, not criminality labels): central
`person_001`, bridges `person_007`/`person_014`, communities A/B/C, call
anomaly `person_003`, transaction anomaly `person_009`, location anomaly
`person_012`. Similar-but-distinct names (e.g. Rahul Sharma / Rahul Verma /
Rohit Sharma) exercise entity resolution.

Run the generator tests:

```bash
python backend/tests/test_generate_data.py
```

> Implemented so far: scaffolding + Phase 1 synthetic data + Phase 2
> ingestion/preprocessing + Phase 3 NLP extraction/entity resolution.
> No graph, analytics, anomaly detection, auth, or dashboard yet.

## Phase 2 — ingestion & preprocessing

Pipeline: upload → file validation → parsing (CSV/JSON/TXT) →
record validation → normalization → processed JSON in `data/processed/`.
Raw files are stored immutably under `data/raw/<TYPE>/` and never modified.

| Endpoint | Purpose |
|---|---|
| `POST /api/upload` | multipart upload (`file`, `dataset_type`, optional `source_name`/`description`) → `201` + `upload_id` (stored, not yet validated) |
| `POST /api/process` | `{"upload_id": ...}` → validate + normalize → `SUCCEEDED`/`PARTIAL`/`FAILED` + `job_id` |
| `GET /api/process/{job_id}` | poll a processing job |

Document metadata lives in a local SQLite store (`DOCUMENT_DB_PATH`,
default `data/processed/documents.db`, git-ignored) mirroring
`DATABASE_SCHEMA.md` documents columns and statuses. PostgreSQL wiring
lands with later phases.

Relevant env vars: `RAW_DATA_DIR`, `PROCESSED_DATA_DIR`,
`DOCUMENT_DB_PATH`, `MAX_UPLOAD_MB` (default 25), `MAX_UPLOAD_RECORDS`
(default 50000).

Run the Phase 2 tests (needs `pip install -r backend/requirements-test.txt`
for the API tests; service tests are stdlib-only):

```bash
python backend/tests/test_ingestion.py
```

Phase 3 contract: processed `records.json` holds standardized records
`{source_id, source_type, upload_id, original, normalized, provenance}` —
see `backend/app/services/ingestion.py`. Phase 3 must consume only these,
never raw formats.

## Phase 3 — NLP extraction & entity resolution

Setup (model is required; services degrade to rules-only without it):

```bash
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm
```

| Endpoint | Purpose |
|---|---|
| `POST /api/entities/extract` | `{"upload_id": ...}` (processed doc) or `{"text": ..., "document_id": ...}` → `{document_id, entities[], relationships: []}` |
| `POST /api/entities/resolve` | `{"document_id": ..., "entities": [...]}` → canonical IDs + `matches` + `resolution_method`; persists entities/mentions |

Resolution methods (explainable, no LLM): `exact_match`, `phone_match`,
`vehicle_match`, `account_match`, `name_similarity` + shared-attribute
evidence, `new_entity`. Similar names without shared evidence never merge.

Run the Phase 3 tests:

```bash
python backend/tests/test_nlp_resolution.py
```

## Phase 4 — Neo4j knowledge graph

Start Neo4j (needs a local-only password; never commit `.env`):

```bash
cp .env.example .env   # set NEO4J_PASSWORD inside
docker compose up -d neo4j
```

| Endpoint | Purpose |
|---|---|
| `GET /api/entities` | canonical entities from the Phase 3 store (filter `type`/`q`, paginated) |
| `GET /api/entities/{id}` | entity detail + mentions + analytics summary (after a run) |
| `GET /api/graph/{id}` | Cytoscape `{nodes, edges, truncated}` neighborhood (bounded depth/limits) |
| `GET /api/graph/{id}/neighbors` | same + `rel_types`/`node_types` filters |
| `POST /api/graph/build` | `{"upload_id"}` → extract → resolve → MERGE graph → verify counts |

Writes are idempotent MERGE keyed by canonical IDs + deterministic edge
IDs (first-write-wins, so rebuilds never modify evidence). `USES` input
converges to `USED` per the schema.

Build the deterministic demo graph and verify it:

```bash
python scripts/build_sample_graph.py
```

Run the Phase 4 tests (fake driver; live test opt-in):

```bash
python backend/tests/test_graph.py
NEO4J_TESTS=1 NEO4J_PASSWORD=<local> python backend/tests/test_neo4j_integration.py
```

## Phase 5 — graph analytics, anomaly detection, priority scoring

Algorithms run over a bounded Neo4j snapshot (undirected projection,
documented in `centrality.py`): degree, PageRank, Brandes betweenness,
deterministic Louvain communities. Anomalies use Isolation Forest
(`random_state=42`) over the 8 fixed features; priority is
`0.35×PageRank + 0.35×Betweenness + 0.30×Anomaly`. All scores are
triage signals — never criminality verdicts.

| Endpoint | Purpose |
|---|---|
| `POST /api/analytics/run` | `{"upload_id"}` or all processed uploads → score + persist run |
| `GET /api/analytics/pagerank` | ranked scores (`?entity_id=`, paginated) |
| `GET /api/analytics/betweenness` | ranked scores (same filters) |
| `GET /api/analytics/communities` | `?community_id=` filter, paginated |
| `GET /api/analytics/degree` | ranked degrees (same filters) |
| `GET /api/anomalies` | `?entity_id=&severity=&min_score=`, paginated |
| `GET /api/investigation/{id}` | priority + metrics + anomaly + explanations + sourced timeline |

Run the Phase 5 tests:

```bash
python backend/tests/test_analytics.py
```

## Phase 6 — API completion, auth, React dashboard

New since Phase 5: JWT auth with server-side RBAC
(`INVESTIGATOR`/`SENIOR_INVESTIGATOR`/`ADMIN`), `GET /api/timeline/{id}`,
`GET /api/search`, user administration, and the full React dashboard
(Dashboard, Network Explorer, Entity Profile + Timeline, Anomalies,
Investigation report, Login, admin Users).

First admin user (password via prompt, never hardcoded):

```bash
python scripts/create_admin.py admin@example.local
```

Required secrets (local-only, never commit): `JWT_SECRET`,
`NEO4J_PASSWORD`. See `.env.example` for the full list
(`JWT_SECRET`, `VITE_API_BASE_URL`, `FRONTEND_URL`, …).

Run backend + dashboard tests:

```bash
python backend/tests/test_auth.py
python backend/tests/test_e2e.py
cd frontend && npm test -- --run && npm run build
```

Manual demo: start services, create admin, log in at
`http://localhost:5173`, upload `data/sample/fir.csv` from the
Dashboard, then explore search → entity profile → graph →
anomalies → investigation report.

## Quickstart

```bash
cp .env.example .env   # fill in local-only values
docker compose up --build
```

- Backend health: `http://localhost:8000/health`
- Frontend: `http://localhost:5173`
- Neo4j browser: `http://localhost:7474`

## Development rules (summary)

- Six phase owners work in parallel against fixed mock contracts.
- Small, isolated changes; no unnecessary dependencies.
- Secrets in env vars only; never commit `.env`.
- Synthetic data only; raw evidence immutable.
- Priority scores are triage aids — never criminality verdicts.
- See `AGENTS.md` for the full binding rules.
