# F2 Knowledge Cards & Hybrid Retrieval Architecture

This documentation details the implementation of the F2 Retrieval layer, built on top of PostgreSQL and Qdrant.

---

## 1. Data Model & Schema Mapping

Each structured Knowledge Card is tracked in PostgreSQL and indexed as one or more vector points in Qdrant.

### 1.1 PostgreSQL Schema (`rag_documents`)
The `rag_documents` table maps tracking info and access controls for active cards:
- `card_id` (UUID, Unique): Canonical card identity issued by the registry.
- `tenant_id` (UUID): Enforced tenant isolation key.
- `card_type` (String): e.g. `Decision`, `Guideline`, `Reference`.
- `card_status` (String): `draft` / `proposed` / `approved` / `superseded` / `obsolete` / `archived`.
- `version` (Integer): Incremental version tag.
- `project` (String): Associated work package.
- `tags` (List of Strings): Custom labels.
- `confidence` (String): Confidence metric.
- `permissions` (String): Access privileges (`public` / `read` / `write`).

### 1.2 Qdrant Payload Attributes
Qdrant points store dense & sparse vectors plus the flat metadata payload:
- `tenant_id`: Mandatory tenant key.
- `status`: Card status (mapped from `card_status`).
- `type`: Card type (mapped from `card_type`).
- `project`, `tags`, `confidence`, `owner`, `language`, `confidentiality`, `permissions`.
- `is_chunk`: Boolean flag for split points.
- `parent_card_id`, `chunk_index`: Grouping references for sibling points.

---

## 2. Multi-Vector Hybrid Search Layer

We configure the Qdrant collections to support named multi-vectors:
1. **`"dense"`**: 1024-dimensional embeddings (computed using BGE-M3 REST service or local deterministic hash fallback).
2. **`"sparse"`**: Sparse tokens and weights list.

### 2.1 Server-Side Fusion (RRF)
Search queries Prefetch results using dense and sparse vectors respectively, then combines candidates via Reciprocal Rank Fusion (RRF):
```python
query=FusionQuery(fusion=Fusion.RRF)
```

---

## 3. Idempotency & Ingestion Endpoints

### 3.1 JSON Direct Ingestion (`POST /collections/{name}/ingest/card`)
Allows direct JSON upload of structured Knowledge Cards:
- Ensures Postgres tracking is registered first.
- Invokes vector store card purges prior to index upsert.

### 3.2 Automated Purges
Before ingesting a card, a point deletion query is executed in Qdrant matching `metadata.card_id` to prevent vector duplication.

---

## 4. Dynamic Security Gates & Retrieval Filtering

All searches execute a dynamic security filter layer resolving roles from JWT claims:
- **Tenant Isolation**: `tenant_id` is strictly matched.
- **Status Gate**: Default query returns `approved` status only. Drafts/archives require Admin/Owner role.
- **Hierarchical RBAC**: Viewer vs Member permission arrays check.
- **Confidentiality restrictions**: High confidentiality cards are only visible to the owner.

---

## 5. Operations & CLI Commands

### 5.1 RAGAS Accuracy Evaluation
Evaluate context accuracy and faithfulness over golden question sets:
```bash
uv run rag_pipeline cmd rag-evaluate --collection documents
```

### 5.2 Restic Backup Verification
Check snapshots integrity and backup stats:
```bash
uv run rag_pipeline cmd rag-backup
```
