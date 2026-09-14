# M1–M3 Implementation Guide

Practical build guide for the F2 Knowledge Card retrieval layer, aligned with the client’s upstream ingestion handoff (Knowledge Layer Spec Steps 1–6 complete on their side; Step 7 will `POST` approved cards to your `/ingest`).

**Related docs**

- Architecture intent: [`f2-platform-design.md`](f2-platform-design.md)
- Gap vs Schedule A: [`requirements-gap-analysis.md`](requirements-gap-analysis.md)
- Current code notes: [`../backend/docs/knowledge_cards.md`](../backend/docs/knowledge_cards.md)
- Runbook: [`../RAG_PIPELINE_GUIDE.md`](../RAG_PIPELINE_GUIDE.md)

---

## 0. What F2 owns (and what it does not)

| F2 owns | External (not your job) |
|---------|-------------------------|
| Qdrant (local Docker for M1–M2; shared from M3+) | Card registry / `card_id` issuance |
| `/ingest` + `/query` (and nested `/api/v1/rag/...` paths today) | Raw archive (S3 etc.) |
| Chunking, BGE-M3 hybrid embeddings | Knowledge agents |
| Mandatory tenant + RBAC + status filters inside Qdrant | Authentik IdP (consume JWT claims only) |
| Access-decision audit logging | Multi-tenant user store |

**CapitalZone tenant zero:** `00000000-0000-0000-0000-000000000000`

**Identity until Authentik:** keep a mock-claims layer. Map session → `tenant_id` + `roles[]`. Never trust tenant/role from the request body.

---

## 1. How the milestones connect

Think of M1 as the **contract and enforcement design**, M2 as the **write path that populates Qdrant with that contract**, and M3 as the **read path that always applies the same filters**.

```text
┌─────────────────────────────────────────────────────────────────┐
│ M1 — Architecture & setup                                       │
│  • Metadata schema (payload shape)                              │
│  • RBAC filter design (mandatory must-conditions)               │
│  • Docker: app + Postgres + Qdrant                              │
│  • Mock claims until Authentik                                  │
│  • /ingest request/response contract (even before full writer)  │
└────────────────────────────┬────────────────────────────────────┘
                             │ same card_id, same payload keys,
                             │ same filter field names
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ M2 — Vector store, ingest, embedding                            │
│  • Accept client card POST (card_id supplied)                   │
│  • Embed (BGE-M3 dense + sparse)                                │
│  • Idempotent upsert (point id = uuid5(card_id))                │
│  • Payload indexes for every filter field                       │
│  • Chunk oversized cards → is_chunk / parent_card_id            │
└────────────────────────────┬────────────────────────────────────┘
                             │ populated index + security payload
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ M3 — Query API with RBAC                                        │
│  • POST /query (and /search)                                    │
│  • Claims → _build_security_filter (never retrieve-then-filter) │
│  • Default status=approved; one tenant_id per request           │
│  • Chunk hit → resolve/collapse to parent card                  │
│  • Audit: decision + filters applied                            │
└─────────────────────────────────────────────────────────────────┘
```

**Non-negotiable continuity rule:** whatever fields M1 designs into the Qdrant payload, M2 must write them on every point, and M3 must filter on them. If M2 omits `role_access`, M3 cannot enforce the client’s RBAC model.

Client timeline note: their Step 7 will call your `/ingest` on card approval. Until then they may write Qdrant directly — your M2 contract still must match their sample payload so integration is drop-in.

---

## 2. Knowledge Card metadata (client-confirmed working set)

### 2.1 Vocabularies (extensible lookups — do not hard-enum in migrations)

Keep string columns / keyword payload fields. Validate lightly (optional allow-list) so Dr. Nazir’s sign-off can change vocab without schema rewrites.

| Field | Working values |
|-------|----------------|
| `type` (`card_type`) | `project`, `process`, `decision`, `lesson_learned`, `best_practice`, `workflow`, `prompt`, `system_tool`, `document`, `known_issue`, `glossary_rule` |
| `confidence` | `validated`, `probable`, `uncertain` |
| `knowledge_class` | `fact`, `decision`, `recommendation`, `inference` |
| `status` | `draft`, `proposed`, `approved`, `superseded`, `obsolete`, `archived` — **queries default to `approved` only** |
| `confidentiality` | `public`, `internal`, `confidential` (names configurable; enforcement model fixed) |

### 2.2 Chunk fields (oversized sources)

| Field | Rule |
|-------|------|
| `is_chunk` | `true` for sibling points of one card |
| `parent_card_id` | parent’s `card_id` |
| `chunk_index` | 0-based order |
| Resolution | A chunk hit must resolve to its parent card (collapse siblings in retrieval) |

### 2.3 Real card shape (ingest contract)

This is what arrives at `/ingest` — **all IDs and payload fields supplied by upstream**. F2 never generates `card_id`.

```json
{
  "card_id": "81b90ff6-6684-4e98-8bb8-8ffbf93af939",
  "tenant_id": "00000000-0000-0000-0000-000000000000",
  "title": "We decided to cache the identity embedding …",
  "type": "decision",
  "status": "approved",
  "version": 1,
  "confidence": "validated",
  "knowledge_class": "decision",
  "area": "video_generation",
  "project": "VEO",
  "applies_to": [],
  "confidentiality": "internal",
  "role_access": ["staff"],
  "owner": "platform-service",
  "language": "en",
  "tags": [],
  "source_pointer": "s3://raw-archive/…/submission…",
  "source_checksum": "e0ecc0af…",
  "source_span": "224:345",
  "document_id": "a37196c3-a7a5-42fb-9024-8882ef79d5a8",
  "is_chunk": false,
  "parent_card_id": null,
  "chunk_index": null,
  "source_created_at": null,
  "created_at": "2026-09-10T14:17:53Z",
  "next_review_at": "2027-03-09T14:17:53Z"
}
```

Also expect `content` (or a file) for the text that gets embedded — content may travel beside this metadata in the handoff payload.

### 2.4 Qdrant payload fields to index

Index at least:

`card_id`, `tenant_id`, `status`, `type`, `area`, `project`, `applies_to`, `version`, `confidence`, `knowledge_class`, `owner`, `language`, `tags`, `is_chunk`, `parent_card_id`, `document_id`, `confidentiality`, `role_access`, plus date fields (`created_at`, `source_created_at`, `next_review_at`, …).

**Idempotency:** upsert keyed by `card_id`. Prefer point ID = `uuid5(card_id)` so re-ingest updates rather than duplicates. Always purge-by-`card_id` before upsert if you keep the current delete-then-insert pattern.

### 2.5 Postgres vs Qdrant

| Store | Role |
|-------|------|
| **PostgreSQL `rag_documents`** | Tracking / audit trail of ingest (status of processing, org link, card metadata mirror) |
| **Qdrant** | Search index: vectors + **security-relevant** metadata copy |

Security fields must live on the Qdrant point so filters run **inside** the query.

### 2.6 Repo field mapping (today → target)

| Client field | Repo today | Action |
|--------------|------------|--------|
| `type` | `card_type` → payload `type` | Keep mapping |
| `status` | `card_status` → payload `status` | Keep mapping; default query `approved` |
| `confidence` | free string | Use client vocab |
| `confidentiality` | `public` / old `low`/`medium`/`high` | **Switch to** `public` / `internal` / `confidential` |
| `role_access` | **missing** (have `permissions` string) | **Add**; make this the RBAC gate |
| `knowledge_class` | **missing** | **Add** |
| `applies_to` | **missing** | **Add** |
| `title` | **missing** on card model | **Add** (return in citations) |
| `permissions` | used in `_build_security_filter` | **Legacy** — stop using for F2 path |

Primary code touchpoints:

- `backend/app/db/models/rag_document.py`
- `backend/app/services/rag/models.py` (`DocumentMetadata`)
- `backend/app/schemas/rag.py`
- `backend/app/services/rag/ingestion.py` (`ingest_card`)
- `backend/app/services/rag/vectorstore.py` (`_ensure_collection`, `_build_payload`)
- `backend/app/services/rag_document.py` + repository

---

## 3. RBAC & access rules (build this in M1, enforce in M3)

### 3.1 Principles (fixed)

1. **Deny by default** — missing permission = denial.
2. Filters are **Qdrant `must` conditions** applied before search — never retrieve-then-filter.
3. **Mandatory on every query:** `tenant_id` + `status` + confidentiality/role gate.
4. **One `tenant_id` per request** — never `OR` across tenants, even if a user has multiple memberships.
5. Role names and confidentiality tier names are **configurable**; the enforcement shape is not.
6. Log every access decision **with the filters applied**.

### 3.2 Working defaults (plug-in config)

```python
# settings / config — swap when roles are signed off
CONFIDENTIALITY_ROLE_MAP = {
    "public": None,                 # unrestricted within tenant + status
    "internal": ["staff"],
    "confidential": ["manager"],
}
```

Card payload carries `role_access: ["staff"]` (keyword array). Session carries `roles: ["staff", ...]`.

### 3.3 Target filter construction

Pseudocode for `_build_security_filter` (replace current `metadata.permissions` ladder):

```text
IF tenant_id missing:
  → must: tenant_id == "DENY_ALL"
  → return

must:
  1. metadata.tenant_id == <session.tenant_id>
  2. metadata.status MatchAny( ["approved"] )
       # only if explicitly permitted (e.g. admin) AND caller passed status_filter:
       #   use that list instead

  3. Access (nested should, still under must):
       OR confidentiality == "public"
       OR (confidentiality IN tiers_allowed_by_session_roles
           AND role_access intersects session.roles)

optional caller filters (type, area, project, tags, …):
  → additional must conditions only — never replace 1–3
```

**How “tiers_allowed_by_session_roles” works**

- For each `(tier, required_roles)` in `CONFIDENTIALITY_ROLE_MAP`:
  - If `required_roles is None` → user may see that tier (public).
  - Else if `session.roles ∩ required_roles` nonempty → user may see that tier **and** the card’s `role_access` must intersect `session.roles`.
- No intersection → that tier is invisible (deny).

### 3.4 What to change in `retrieval.py`

File: `backend/app/services/rag/retrieval.py` → `_build_security_filter`

| Keep | Change |
|------|--------|
| Deny-all when `tenant_id` missing | — |
| Default `status` = `approved` | — |
| Admin/owner status override (if still desired) | Confirm with client who may override |
| Custom filters additive | — |
| Chunk collapse via `parent_card_id` | — |
| Filter on `metadata.permissions` | **Replace with** `confidentiality` + `role_access` + config map |
| Confidentiality `low`/`medium`/`high` + owner bypass | **Replace with** public/internal/confidential model |

Claims input should eventually be `roles: list[str]` (Authentik). Until then, mock claims that emit the same shape.

### 3.5 Audit

On every `/search` and `/query`:

- Actor, tenant_id, roles, collection
- Filters applied (status list, confidentiality rule version / map id)
- Decision (`allow` with result count; prefer also logging empty/deny contexts)
- **Do not** log raw query text or chunk bodies if confidentiality forbids it

---

## 4. How to build M1 — Architecture & setup

**Goal:** Lock the schema, filter design, local stack, and ingest/query **contracts** so M2/M3 implement against a stable interface.

### 4.1 Deliverables checklist

- [ ] Docker Compose: `app`, Postgres 16, Qdrant (align toward client interim **v1.12.4** + API key when integrating; local M1–M2 can stay on current compose version if documented)
- [ ] Documented metadata schema (this guide §2) reflected in models/schemas
- [ ] Documented RBAC filter design (this guide §3) — even if full enforcement lands in M3
- [ ] Mock claims: `tenant_id` + `roles[]` (CapitalZone UUID for demos)
- [ ] Draft `/ingest` request/response contract matching client sample (+ `content`)
- [ ] Collection naming convention: client uses **`kb_{area}`** (e.g. `kb_video_generation`) — plan for it even if current API uses arbitrary collection names

### 4.2 Implementation steps

1. **Extend models** — add `title`, `knowledge_class`, `applies_to`, `role_access` (array) on `RAGDocument` + `DocumentMetadata` + Pydantic ingest schemas. Keep `permissions` only if needed for old seeds; do not use it in new filter design.
2. **Alembic migration** for new columns (`ARRAY` for `role_access` / `applies_to`).
3. **Config module** — `CONFIDENTIALITY_ROLE_MAP` + allowed vocab lists (optional validation).
4. **Write M1 architecture note** into API OpenAPI descriptions / this doc — especially: card_id never generated; one tenant per request; filters inside Qdrant.
5. **Unit-test stubs** — tests that assert filter *shape* for staff vs manager vs no-role (can land fully in M3; scaffold in M1).

### 4.3 Exit criteria for M1

You can answer “yes” to:

- What exact JSON does `/ingest` accept?
- Which payload keys are indexed in Qdrant?
- What three mandatory filters run on every query?
- How does mock claims → filter inputs work?

---

## 5. How to build M2 — Vector store, ingest, embeddings

**Goal:** Persist client cards into Qdrant with correct payload and embeddings so M3 has a realistic index.

### 5.1 Deliverables checklist

- [ ] `POST …/ingest` (or `…/ingest/card`) accepts full client card + content
- [ ] Idempotent per `card_id` (delete-by-card_id and/or `uuid5(card_id)` point ids)
- [ ] BGE-M3 dense (1024) + sparse; hybrid collection config
- [ ] Payload indexes for all §2.4 fields including `role_access`, `knowledge_class`, `applies_to`
- [ ] Oversized content → chunk points with `is_chunk` / `parent_card_id` / `chunk_index`
- [ ] Postgres row created/updated for tracking
- [ ] Local Qdrant via Docker with API-key auth ready for M3 shared instance

### 5.2 Implementation steps

1. **Align ingest schema** with client sample (`type`/`status` at API edge; map to internal `card_type`/`card_status` if you keep DB names).
2. **`ingest_card`** — pass through new fields into `DocumentMetadata`; stop requiring `permissions` for the F2 path; set `role_access` default from confidentiality map if upstream omits it (prefer fail-closed: empty `role_access` + non-public = invisible).
3. **`vectorstore._ensure_collection`** — create missing payload indexes; named vectors `dense` + `sparse`.
4. **Point IDs** — `uuid.uuid5(NAMESPACE_URL, card_id)` for single-card points; for chunks use `uuid5(..., f"{card_id}:{chunk_index}")`.
5. **Embeddings** — wire `BGEM3_ENDPOINT_URL`; document fallback behavior (OpenAI/mock) as non-production.
6. **Collection naming** — support `kb_{area}` (derive from card `area` or require caller to pass collection name consistently).
7. **Tests** — `test_ingestion.py`: upsert twice → one logical card; chunk flags set; payload contains `role_access` / `tenant_id` / `status`.

### 5.3 Ingest flow

```text
Client Step 7 (or curl/Swagger)
  POST /api/v1/rag/collections/{kb_area}/ingest/card
  body: card metadata + content
       │
       ▼
  Validate tenant_id, card_id present
       │
       ▼
  Upsert rag_documents (Postgres tracking)
       │
       ▼
  delete_card(card_id) / overwrite uuid5 points
       │
       ▼
  Chunk if needed → embed each piece → upsert Qdrant
       │
       ▼
  Response: card_id, chunk_count, status
```

### 5.4 Exit criteria for M2

- Re-POSTing the same `card_id` updates vectors/payload, does not duplicate.
- Qdrant point payload can satisfy every M3 mandatory filter key.
- A staff-scoped `internal` card is visible in raw Qdrant payload inspection with `role_access: ["staff"]`.

---

## 6. How to build M3 — RBAC, tenant & query API

**Goal:** Every search goes through the M1 filter design against the M2 index.

### 6.1 Deliverables checklist

- [ ] `POST /query` and `POST /search` require auth
- [ ] `tenant_id` and `roles` from session/mock claims only
- [ ] `_build_security_filter` implements §3.3
- [ ] Default `status=approved`
- [ ] Optional filters: `type`, `area`, `project`, `tags`, `confidence`, `knowledge_class`, …
- [ ] Citations: `card_id`, `score`, `source_pointer` (+ title/type/status/version when present)
- [ ] Chunk collapse / parent resolution
- [ ] Audit log of decision + filters
- [ ] Tests: cross-tenant isolation, staff sees internal, viewer without staff does not, confidential needs manager

### 6.2 Implementation steps

1. **Deps** — resolve `ActiveOrg` / mock Authentik claims → `tenant_id=str(...)`, `roles=["staff"]`.
2. **Rewrite `_build_security_filter`** — drop `permissions` ladder; implement confidentiality × `role_access`.
3. **Routes** — `rag.py` `search_documents` / `query_knowledge_base`: pass claims into retrieval; strip tenant from body filters.
4. **Agent tool parity** — if `rag_tool.py` calls retrieve, pass the same tenant/roles (today it may omit them → deny-all or unsafe later).
5. **Audit** — extend `record_audit` details with filter snapshot.
6. **Tests** — update `test_rbac_retrieval.py` for the new model; add HTTP-level tenant A vs B test if missing.

### 6.3 Query flow

```text
POST /api/v1/rag/query + JWT/mock
  → Extract tenant_id, roles[]  (exactly one tenant)
  → Build Filter (mandatory + optional)
  → Hybrid search (dense + sparse, RRF) WITH filter
  → Collapse chunks by parent_card_id
  → LLM answer (optional /query) + citations
  → record_audit(decision, filters, result_count)
```

### 6.4 Exit criteria for M3

- Missing tenant → zero results (deny-all).
- Draft cards never appear unless explicitly and permissibly overridden.
- `internal` card with `role_access: ["staff"]` returned for staff session; not for a session with no matching roles.
- Tenant B cannot read Tenant A points even with identical roles.
- Audit row exists for the query with filter metadata.

---

## 7. Suggested build order (week plan)

| Order | Work | Milestone | Why first |
|------|------|-----------|-----------|
| 1 | Metadata fields + migration + ingest schema | M1→M2 | Writers and filters need the same keys |
| 2 | Payload indexes + `uuid5` point ids | M2 | Stable upsert contract |
| 3 | Config map + rewrite `_build_security_filter` | M1 design / M3 code | Can unit-test without full embeddings |
| 4 | Wire claims into `/search` + `/query` | M3 | End-to-end enforcement |
| 5 | BGE-M3 endpoint + hybrid verify | M2 polish | Retrieval quality |
| 6 | Audit enrichment + isolation tests | M3 / M4-adjacent | Proof for client |
| 7 | Collection `kb_{area}` + Qdrant version/API key align | M2/M3 integration | Match their interim env |

Do **not** wait for final role vocabulary sign-off — use the working map and keep it config-driven.

---

## 8. File map (where to implement)

| Concern | Path |
|---------|------|
| Card columns | `backend/app/db/models/rag_document.py` |
| In-memory metadata | `backend/app/services/rag/models.py` |
| HTTP schemas | `backend/app/schemas/rag.py` |
| Ingest orchestration | `backend/app/services/rag/ingestion.py` |
| Postgres tracking service | `backend/app/services/rag_document.py` |
| Qdrant upsert + indexes | `backend/app/services/rag/vectorstore.py` |
| Embeddings | `backend/app/services/rag/embeddings.py` |
| **RBAC filter** | `backend/app/services/rag/retrieval.py` |
| Routes | `backend/app/api/routes/v1/rag.py` |
| Auth / org context | `backend/app/api/deps.py` |
| Audit | `backend/app/core/audit.py` |
| Filter unit tests | `backend/tests/test_rbac_retrieval.py` |
| Ingest tests | `backend/tests/test_ingestion.py` |
| Compose / Qdrant | `docker-compose.yml` |

---

## 9. Quick verification script (after M2+M3)

Use CapitalZone tenant and a staff role in mock claims.

1. Ingest the sample decision card (`confidentiality: internal`, `role_access: ["staff"]`, `status: approved`).
2. Query as staff in tenant zero → expect hit + citation `card_id`.
3. Query as session with roles `[]` → expect no hit.
4. Ingest duplicate `card_id` with edited text → still one card family in results.
5. Ingest `status: draft` → default query hides it.
6. Ingest second tenant UUID → staff in tenant zero must not see it.

---

## 10. Open items (do not block Week 1)

| Item | Status |
|------|--------|
| Final role vocabulary / Authentik claim names | Pending sign-off — keep config map |
| Exact role → confidentiality matrix beyond working defaults | Plug-in later |
| Shared Qdrant from M3+ | Local Docker until then; target v1.12.4 + API key for parity |
| Org GitHub repo transfer | Work in private repo until invite |
| Bare `/ingest` vs `/api/v1/rag/collections/{name}/ingest/card` | Contract alias / path alignment when client shares final OpenAPI |

---

## 11. Bottom line

- **M1** defines the card payload and the mandatory Qdrant filter contract (tenant + approved + confidentiality/`role_access`).
- **M2** writes that exact payload (with embeddings and idempotent `card_id` upsert) so the index is realistic.
- **M3** reads only through that filter, from session claims, with audit — never retrieve-then-filter, never multi-tenant OR.

Implement metadata + config map first, then ingest writers, then replace `_build_security_filter` and lock it with tests. Everything else (BGE-M3 polish, shared Qdrant, Authentik) plugs into the same seams.
