# NEO4J_SCHEMA.md — Crime Network Intelligence System (Knowledge Graph)

> Authoritative contract for the Neo4j knowledge graph. Binding per `AGENTS.md` §6 and `PROJECT_SPEC.md` §21.
> Neo4j stores entities, relationships, traversal, and analytics input. PostgreSQL stores application metadata. Do not duplicate PostgreSQL tables in Neo4j.
> All examples use synthetic data. Scores are investigation-support signals, never guilt or proof of criminality.

---

## 1. NEO4J RESPONSIBILITY

Neo4j is responsible for:

- Knowledge graph storage
- Entity relationships
- Graph traversal
- Relationship exploration
- Graph-oriented investigation queries
- Graph analytics input

PostgreSQL remains responsible for structured application metadata (users, documents, mentions, investigations, anomalies, audit logs per `DATABASE_SCHEMA.md`).

Rules:

- Do not unnecessarily duplicate PostgreSQL application tables inside Neo4j. Neo4j holds graph nodes + edges + provenance refs, not auth/audit/upload tables.
- Neo4j is a derived representation of source evidence, not the evidence itself (§22).
- Analytics read from Neo4j; score persistence lives in PostgreSQL (`anomalies`) + API payloads.

---

## 2. NODE TYPES

Initial graph node labels (fixed, v1):

```text
Person
Phone
Location
Vehicle
Organization
BankAccount
FIR
Crime
```

Mapping to entity types (`PROJECT_SPEC.md` §4): `PERSON→Person, PHONE→Phone, LOCATION→Location, VEHICLE→Vehicle, ORGANIZATION→Organization, ACCOUNT→BankAccount, DATE→property (ISO 8601, not a node unless required), FIR→FIR, Crime→Crime`.

Do not add labels without §30 change process.

---

## 3. PERSON NODE

Label: `Person`.

Properties:

- `id` (TEXT, required) — stable canonical ID, e.g. `person_001`
- `name` (TEXT, required) — display value, e.g. `Rahul Sharma`
- `normalized_name` (TEXT, required) — matching/search form, e.g. `rahul sharma`
- `risk_score` (FLOAT, optional) — cached investigation-priority signal `0–1` where applicable

Example:

```cypher
(:Person {
  id: "person_001",
  name: "Rahul Sharma",
  normalized_name: "rahul sharma"
})
```

Requirements:

- `id` stable and unique (constraint §18); never reused across distinct people.
- `normalized_name` deterministic (lowercase, trimmed, collapsed spacing) for matching/search.
- Do not treat `risk_score` as proof of criminality. If present, it mirrors the API priority score with formula version in surrounding payload, never as a standalone verdict. Prefer computing scores in analytics jobs over storing them as source truth.

---

## 4. PHONE NODE

Label: `Phone`.

Properties:

- `id` (TEXT, required) — e.g. `phone_001`
- `number` (TEXT, required) — normalized E.164-ish form, e.g. `+919876543210`

Example:

```cypher
(:Phone {
  id: "phone_001",
  number: "+919876543210"
})
```

Phone numbers must be normalized before graph insertion (strip spaces/dashes, normalize country prefix, validate digit length; reject malformed with error, never silently coerce two distinct numbers together).

---

## 5. LOCATION NODE

Label: `Location`.

Properties:

- `id` (TEXT, required)
- `name` (TEXT, required) — e.g. `Andheri West, Mumbai`
- `latitude` (FLOAT, optional)
- `longitude` (FLOAT, optional)

Latitude/longitude optional when unavailable. When present: WGS84 decimal degrees, `latitude -90..90`, `longitude -180..180`. Never fabricate coordinates; `null` preferred over guessed values.

---

## 6. VEHICLE NODE

Label: `Vehicle`.

Properties:

- `id` (TEXT, required)
- `registration_number` (TEXT, required) — normalized form, e.g. `MH02AB1234`

Registration numbers normalized where appropriate (uppercase, strip spaces/hyphens, validate format per issuing convention; preserve original mention text in PostgreSQL `entity_mentions.text`, graph holds canonical form + `source_record_id` on the linking edge).

---

## 7. ORGANIZATION NODE

Label: `Organization`.

Properties:

- `id` (TEXT, required)
- `name` (TEXT, required)
- `normalized_name` (TEXT, required)

Same normalization discipline as `Person.normalized_name`.

---

## 8. BANK ACCOUNT NODE

Label: `BankAccount`.

Properties:

- `id` (TEXT, required) — canonical account node id, e.g. `ACC001`
- `account_number` (TEXT, required) — canonical account reference

Avoid exposing full account numbers unnecessarily through APIs or logs. API layer masks/truncates (e.g., `XXXXXX1234`) unless the caller's role explicitly requires full value; logs never contain full numbers.

---

## 9. FIR NODE

Label: `FIR`.

Properties:

- `id` (TEXT, required) — e.g. `FIR_001` (matches PostgreSQL `documents.id` where applicable)
- `date` (TEXT/DATE, required) — ISO 8601
- `text` (TEXT, optional/summarized) — excerpt or digest, not necessarily full FIR body
- `police_station` (TEXT, optional) — where available

Original source/provenance must remain traceable (`document_id`/`source_record_id` on `MENTIONED_IN` edges + PostgreSQL `documents`/`entity_mentions`).

Do not treat FIR content as automatically verified facts. FIR text is an allegation/report (extraction source), not ground truth — propagate this distinction into explanations and UI copy.

---

## 10. CRIME NODE

Label: `Crime`.

Properties (may include):

- `id` (TEXT, required) — e.g. `crime_001`
- `type` (TEXT, optional) — classification from source, e.g. `THEFT`
- `description` (TEXT, optional) — source wording
- `date` (TEXT/DATE, optional) — ISO 8601

Crime nodes represent information present in source data (offence as reported/classified).

Do not automatically infer that an entity committed a crime merely because they are connected to a `Crime` node. Connection (e.g., `MENTIONED_IN`, proximity) is not attribution; attribution requires explicit sourced edge + human interpretation.

---

## 11. RELATIONSHIPS

Supported relationship types (fixed, v1):

```text
CALLED
MET
LOCATED_AT
OWNS
USED
TRANSFERRED_TO
ASSOCIATED_WITH
MENTIONED_IN
WORKS_FOR
TRAVELLED_TO
```

No other types without §30. Direction matters and is defined per §12–§14. Storing the reverse duplicate edge is forbidden (traverse both directions in queries instead).

---

## 12. PERSON RELATIONSHIPS

Canonical person-centric examples (direction fixed):

```cypher
(Person)-[:CALLED]->(Person)
(Person)-[:MET]->(Person)
(Person)-[:LOCATED_AT]->(Location)
(Person)-[:OWNS]->(BankAccount)
(Person)-[:USED]->(Vehicle)
(Person)-[:WORKS_FOR]->(Organization)
(Person)-[:MENTIONED_IN]->(FIR)
(Person)-[:TRAVELLED_TO]->(Location)
```

Notes:

- `CALLED` between `Person` nodes is a resolved person-level summary of phone-level CDR evidence. The underlying `Phone–Phone`/`Phone–CDR` trace must remain reachable via edge `source_record_id` → CDR record (see §13).
- `MENTIONED_IN` always points toward `FIR` (entity → document), anchoring provenance.
- `OWNS`/`USED`/`WORKS_FOR` require source evidence or explicitly marked inference (method + confidence + provenance, §16).

---

## 13. PHONE RELATIONSHIPS

Phone linkage pattern:

```cypher
(Person)-[:USES]->(Phone)
```

> Naming note: the canonical person-to-phone link is `USES` in existing loaders; the §11 fixed vocabulary governs person↔entity semantics via `USED`/`OWNS`. Implementations MUST NOT silently invent additional types: use `USED` for person→phone/vehicle usage. If `USES` exists in legacy data, treat it as an alias of `USED` during migration and converge on `USED`, documenting the rename via §30. New writes use `USED`.

If the project uses `CALLED` between `Person` nodes, the phone/CDR source information must still remain traceable: every `CALLED` edge carries `source_record_id` (CDR id) + optional `via_phones: [calling_number, called_number]` in edge properties, resolvable to `Phone` nodes and PostgreSQL documents.

---

## 14. BANK TRANSACTION

Financial transfers use account-to-account edges:

```cypher
(BankAccount)-[:TRANSFERRED_TO]->(BankAccount)
```

Relationship properties may include `transaction_id`, `amount`, `currency`, `timestamp`, `source_id`.

Example:

```cypher
(:BankAccount {id: "ACC001"})
  -[:TRANSFERRED_TO {
      transaction_id: "TXN001",
      amount: 850000,
      currency: "INR",
      timestamp: "2026-08-12T13:40:00",
      source_id: "TXN001"
    }]->
(:BankAccount {id: "ACC002"})
```

- `amount` numeric `≥ 0`; `currency` ISO 4217 (`INR` etc.); `timestamp` ISO 8601; `transaction_id`/`source_id` traceable to source transaction record.
- One edge per transaction (no aggregation into summed edges without separate aggregate edge type + approval). Duplicate ingestion must not duplicate edges (§21).

---

## 15. RELATIONSHIP PROPERTIES

Where appropriate, relationships may contain: `id`, `timestamp`, `duration`, `confidence`, `source_id`, `source_record_id`.

Example:

```cypher
(Person)-[:CALLED {
  id: "rel_001",
  timestamp: "2026-08-12T10:32:00",
  duration: 420,
  confidence: 0.96,
  source_record_id: "CDR_001"
}]->(Person)
```

- `id` unique per edge (for API `edges[].id`); `timestamp` ISO 8601; `duration` seconds `≥ 0`; `confidence 0–1`; `source_record_id` required for evidence-backed edges.
- Do not add arbitrary properties without justification. New properties require: use case, type/range, API exposure decision, §30 update if contract-visible.

---

## 16. PROVENANCE

Graph information must retain provenance where practical. Every important extracted/inferred relationship traceable to its source.

Provenance fields: `source_id`, `document_id`, `source_record_id`, `timestamp`, `confidence`.

Rules:

- Evidence-backed edges: `source_record_id` (+ `document_id` where resolvable) required.
- Inferred edges: additionally `inference_method` + `confidence`, and UI/API must label them inferred.
- Never create unsupported relationships merely to make the graph look more connected. Sparseness with provenance beats density without it.

---

## 17. ENTITY RESOLUTION

Neo4j uses canonical entity IDs after resolution. Example:

Different mentions `Rahul Sharma` / `R. Sharma` / `Rahul S.` may resolve to `person_001`, and only `person_001` becomes the `Person.id` in Neo4j.

- Original mentions remain traceable through PostgreSQL (`entity_mentions.text`, `document_id`, `confidence`, `extraction_method`).
- Do not merge entities directly in Neo4j merely because names are similar. Resolution happens before canonical insertion (NLP/resolution service decides; graph loader consumes canonical IDs).
- Merge corrections: keep losing IDs as retired aliases in PostgreSQL; never reassign a retired `id` to a different entity; graph rewrites use explicit remap jobs with audit entries.

---

## 18. CONSTRAINTS & INDEXES

Uniqueness constraints — canonical `id` unique per label (Neo4j 5+ syntax; adjust only for version compat, never weaken):

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT phone_id_unique IF NOT EXISTS FOR (n:Phone) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (n:Location) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT vehicle_id_unique IF NOT EXISTS FOR (n:Vehicle) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT organization_id_unique IF NOT EXISTS FOR (n:Organization) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT bankaccount_id_unique IF NOT EXISTS FOR (n:BankAccount) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT fir_id_unique IF NOT EXISTS FOR (n:FIR) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT crime_id_unique IF NOT EXISTS FOR (n:Crime) REQUIRE n.id IS UNIQUE;
```

Indexes for frequent search (justify before adding more):

```cypher
CREATE INDEX person_normalized_name IF NOT EXISTS FOR (n:Person) ON (n.normalized_name);
CREATE INDEX person_name IF NOT EXISTS FOR (n:Person) ON (n.name);
CREATE INDEX phone_number IF NOT EXISTS FOR (n:Phone) ON (n.number);
CREATE INDEX vehicle_reg IF NOT EXISTS FOR (n:Vehicle) ON (n.registration_number);
CREATE INDEX org_normalized_name IF NOT EXISTS FOR (n:Organization) ON (n.normalized_name);
CREATE INDEX location_name IF NOT EXISTS FOR (n:Location) ON (n.name);
```

Use syntax compatible with the project's selected Neo4j version (pin version in deployment config; 4.x fallback `CREATE CONSTRAINT ... ASSERT n.id IS UNIQUE` documented at implementation time, not as silent drift).

---

## 19. CYPHER SAFETY

- Never accept arbitrary Cypher from the frontend. No `query`/`cypher` request fields; reject with `400/422` if detected.
- Application code uses parameterized Cypher only (`$id`, `$depth`, `$limit`, `$relTypes`). Never string-concatenate user input into Cypher.
- Validate server-side: node IDs (pattern `^[A-Za-z0-9_-]{1,64}$`), relationship types (allowlist §11), filters (enums/ranges), traversal depth (≤ max §20), pagination/limits (clamped §20).
- Never allow unrestricted traversal from user-controlled parameters. Depth, node/edge caps, and timeouts enforced in code, not trusted from the client.

---

## 20. GRAPH TRAVERSAL LIMITS

Graph APIs enforce sensible limits (defaults per `API_SPEC.md` §4/§13; hard caps here):

- Maximum traversal depth: default 1, hard max 3.
- Maximum neighbors per query: default 100 nodes / 300 edges; hard max 500 nodes / 1500 edges.
- Maximum returned nodes/relationships per response: hard caps above; `truncated: true` when hit.
- Query timeout: bounded (e.g., 10s); timeout → `503` with retry guidance, never partial graph claimed as complete.

Never expose an endpoint that can request the entire graph without explicit administrative justification (admin-only export with audit entry + streaming/pagination).

---

## 21. DATA INTEGRITY

- Construction deterministic and repeatable: same valid input ⇒ same canonical nodes/edges, no duplicates.
- Use `MERGE` on canonical `id` for nodes: `MERGE (n:Person {id: $id}) ON CREATE SET ... ON MATCH SET ...` (update only non-identity props + provenance append, never reassign identity).
- Do not `MERGE` on non-unique props (e.g., `name`) — that merges distinct entities. Identity key is `id` (+ label) only.
- Relationship dedupe: `MERGE` on `(source_id, target_id, type, source_record_id)` or stable edge `id`; re-ingestion of the same record is idempotent. Distinct records between the same endpoints create distinct edges (or explicitly approved aggregated edges).

---

## 22. RAW DATA VS GRAPH DATA

- Neo4j is derived representation. Original raw documents/data live in source/document storage (PostgreSQL `documents` + file store), never only in the graph.
- Neo4j retains references (`source_id`, `document_id`, `source_record_id`, `timestamp`, `confidence`) to navigate back to evidence.
- Never treat the graph as replacement for original evidence. Deleting source documents does not cascade-delete graph without explicit reviewed procedure + audit; graph edits never rewrite source rows.

---

## 23. ANALYTICS COMPATIBILITY

Graph must support Degree Centrality, PageRank, Betweenness Centrality, Community Detection (via Neo4j GDS or approved batch jobs).

- Analytics run over stable entity IDs; results keyed by canonical `id` (joinable to PostgreSQL `entities`/`anomalies` and API payloads).
- Analytics results must not modify source evidence. Score writeback (if any) limited to designated score properties (e.g., `Person.risk_score` with formula version alongside) or — preferred — external score store; never overwrite identity/provenance properties.

---

## 24. INVESTIGATION PRIORITY

Graph metrics may contribute to Investigation Priority Score:

```text
0.35 × PageRank + 0.35 × Betweenness + 0.30 × Anomaly Score
```

- Computation owned by analytics service, not by graph writes. Components normalized `[0,1]`; weights fixed (change via spec approval only).
- Score is investigation-support signal. It must NOT be represented as guilt, probability of criminality, proof of criminal activity, or prediction of future crime — in node properties, query names, API output, or UI copy.

---

## 25. GRAPH QUERY EXAMPLES

Safe parameterized examples (all `$`-params, validated + limited). Never interpolate user input.

Find entity by ID:

```cypher
MATCH (n:Person {id: $id})
RETURN n LIMIT 1
```

Direct neighbors (bounded, type-filtered):

```cypher
MATCH (n {id: $id})-[r]-(m)
WHERE ($relTypes IS NULL OR type(r) IN $relTypes)
RETURN n, r, m
LIMIT $limit
```

Within N hops (depth validated ≤ 3):

```cypher
MATCH p = (n {id: $id})-[*1..$depth]-(m)
WHERE ($relTypes IS NULL OR ALL(r IN relationships(p) WHERE type(r) IN $relTypes))
RETURN p LIMIT $limit
```

Communication relationships:

```cypher
MATCH (a:Person {id: $id})-[r:CALLED]-(b:Person)
RETURN a, r, b ORDER BY r.timestamp DESC LIMIT $limit
```

Transaction relationships:

```cypher
MATCH (a:BankAccount {id: $id})-[r:TRANSFERRED_TO]-(b:BankAccount)
RETURN a, r, b ORDER BY r.timestamp DESC LIMIT $limit
```

Entities at a location:

```cypher
MATCH (n)-[r:LOCATED_AT|TRAVELLED_TO]->(l:Location {id: $locationId})
RETURN n, r, l LIMIT $limit
```

Bridge-like entities (betweenness input — illustrative; actual metric via GDS/analytics job):

```cypher
MATCH (a:Person)-[*2..2]-(b:Person) WHERE a <> b
WITH a AS bridge, count(DISTINCT b) AS reach
RETURN bridge.id AS id, reach ORDER BY reach DESC LIMIT $limit
```

Cytoscape.js payload: backend maps `n.id → nodes[].id`, display name → `label`, label → `type` (uppercase entity type), `r` → `edges[]` with `source/target/type` + optional `metadata {confidence, timestamp, source_id}` per `API_SPEC.md` §4. Transformation tested (§29).

---

## 26. GRAPH API OUTPUT

Neo4j results transformed to (`API_SPEC.md` §4):

```json
{
  "nodes": [{"id": "P001", "label": "Rahul Sharma", "type": "PERSON"}],
  "edges": [{"id": "R001", "source": "P001", "target": "P002", "type": "CALLED"}]
}
```

Optional metadata: `confidence`, `timestamp`, `source_id`, relationship properties (§15).

- `type` mapping: Neo4j label → API type (`Person→PERSON`, `BankAccount→ACCOUNT`, etc.).
- Masking: `BankAccount` numbers truncated in `label`/metadata unless authorized; no secrets/paths in payloads.
- Provenance preserved where available; missing provenance → `null` + `provenance_status: "missing"`, never silent drop.

---

## 27. SECURITY

- Neo4j credentials from environment variables/secrets only; never in code, config commits, logs, or frontend.
- Neo4j not publicly exposed; Docker-internal network, authenticated + TLS where beyond localhost; least-privilege graph roles.
- Application users never receive direct Neo4j credentials. No per-user Bolt access; all access via backend service account.
- Frontend never connects directly to Neo4j (no Bolt/HTTP from React; API only).
- Backend enforces authorization (role checks per `API_SPEC.md` §10) before any graph read/write.
- Cypher parameterized (§19); results limited (§20); sensitive properties masked (§8, §26); errors generic (no Cypher echo).

---

## 28. AUDITABILITY

Important graph modifications traceable to: user/action where applicable, source document, source record, processing operation, timestamp.

- Loader jobs emit PostgreSQL `audit_logs` entries (hash-chained) referencing affected node/edge ids + source ids + job id. Graph stores provenance refs; audit authority lives in `audit_logs`, not in Neo4j.
- Graph itself is not the authoritative audit log. Never reconstruct compliance history from graph alone.

---

## 29. TESTING

Required graph tests:

- node creation per label with required props.
- duplicate prevention (re-ingest same canonical id ⇒ single node).
- relationship creation with correct direction + allowed type.
- relationship properties persisted (timestamp/confidence/source_record_id).
- provenance present on evidence edges; inferred edges labeled.
- entity resolution output consumed correctly (aliases → one canonical node; distinct people stay distinct).
- Cypher parameterization (injection strings rejected/escaped; no interpolation).
- traversal limits enforced (depth/node/edge caps, `truncated` flag, timeout behavior).
- nonexistent IDs return empty/404, not errors leaking internals.
- graph API transformation (Neo4j record → Cytoscape `nodes/edges` golden shape).
- transaction failure handling (failed write ⇒ no partial nodes/edges; caller reports failure, never false success).

---

## 30. SCHEMA CHANGE POLICY

`NEO4J_SCHEMA.md` is an architectural contract. New node type, relationship type, property, constraint, or major graph behavior requires:

1. Identify the change.
2. Explain why it is needed.
3. Identify affected services/APIs/analytics.
4. Update `NEO4J_SCHEMA.md`.
5. Update tests.
6. Update implementation.

Never silently change the graph schema. Prefer additive, backward-compatible changes.
