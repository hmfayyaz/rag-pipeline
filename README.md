# F2 Knowledge Base & Hybrid Retrieval Pipeline

A production-ready FastAPI backend service implementing the **F2 Technical Specification for Retrieval Layers**, featuring PostgreSQL metadata tracking and Qdrant named multi-vector (hybrid dense/sparse) search.

---

## 🚀 Core Features

*   **Idempotent Ingestion:** Direct JSON ingestion `/collections/{name}/ingest/card` ensuring that older versions of the card matching `card_id` are automatically purged from Qdrant before upserting the new point versions.
*   **Named Hybrid Vectors:** Qdrant collection configured with named multi-vectors:
    *   `"dense"` (1024-dimension BGE-M3 semantic vectors).
    *   `"sparse"` (Sparse vector weights for keyword queries).
*   **Reciprocal Rank Fusion (RRF):** Merges dense semantic searches and sparse keyword queries server-side via Qdrant's prefetch query API.
*   **Dynamic Security Gate:** Parses incoming JWT claims (e.g. Authentik integration) to enforce:
    *   *Tenant Isolation:* Mandatorily scoping searches by `tenant_id`.
    *   *Status Boundaries:* Rejecting draft/archive cards for standard Viewer/Member roles, allowing only Owner/Admin bypass.
    *   *RBAC Permissions Check:* Matching permissions key attributes (`public`, `read`, `write`, `viewer`, `member`).
*   **Chunk Aggregation & Collapsing:** Segments cards exceeding length limits (>8000 characters) into deterministically-mapped sibling points, and automatically collapses hits by `parent_card_id` to optimize token usage.

---

## 🛠️ Technology Stack

*   **Core Framework:** FastAPI + Pydantic v2
*   **Database:** PostgreSQL (Async queries via SQLAlchemy + asyncpg)
*   **Vector Engine:** Qdrant Vector DB
*   **Embeddings:** BGE-M3 REST Service (with automated fallback tokenizers for offline local dev)
*   **Tests:** Pytest async suite

---

## 🚀 Quick Start (Local Dev)

### 1. Boot up Infrastructure Services
Spin up PostgreSQL, Redis, and Qdrant locally:
```bash
docker compose up -d
```

### 2. Backend Environment Setup
Navigate to the `backend` directory, install dependencies, and run migrations:
```bash
cd backend
uv sync --dev
uv run alembic upgrade head
```

### 3. Start Backend Server
```bash
uv run uvicorn app.main:app --reload --port 8000
```
Access the clean Swagger API documentation at: **http://localhost:8000/docs**

---

## 🧪 Testing & Verification

Run the full backend test suite to verify RAG operations, status boundaries, and multi-tenant isolation:
```bash
cd backend
uv run python -m pytest tests/
```

---

## 📊 Click CLI Commands

The application registers auto-discovered custom commands to simplify testing and RAG management.

```bash
# Seed initial PostgreSQL database context
uv run rag_pipeline cmd seed

# Run local RAGAS accuracy evaluation runner
uv run rag_pipeline cmd rag-evaluate --collection documents

# Verify restic backup pipeline configurations and snapshot checks
uv run rag_pipeline cmd rag-backup

# Reset all PostgreSQL database and Qdrant vector segments
uv run rag_pipeline cmd reset-demo
```

---

## 📂 Project Structure

```
backend/
├── app/
│   ├── api/routes/v1/    # REST endpoints (health, auth, users, rag, dev)
│   ├── services/         # Business logic (RAG ingestion, retrieval, vectorstore)
│   ├── repositories/     # Data access layer
│   ├── db/models/        # PostgreSQL declarative models
│   ├── schemas/          # Pydantic data schemas
│   └── commands/         # Custom CLI commands (rag-evaluate, seed, reset-demo)
└── tests/                # Async pytests suite
```

For a detailed walkthrough of the architectural choices, see the [Knowledge Cards Docs](backend/docs/knowledge_cards.md).

---

## 🛠️ Step-by-Step Manual Verification Guide

You can easily verify the entire F2 retrieve-and-ingest flow manually by following these steps.

### Step 1: Initialize Database & Seed
Run database migrations and seed default organizations, users, and API keys:
```bash
cd backend
uv run alembic upgrade head
uv run rag_pipeline cmd seed
```

### Step 2: Start the Backend Dev Server
```bash
uv run uvicorn app.main:app --reload --port 8000
```
Open **http://localhost:8000/docs** in your browser to access the Swagger UI.

### Step 3: Authenticate and Obtain JWT Token
To authenticate endpoints, you can log in as the default Admin created during seeding:
- **Endpoint:** `POST /api/v1/auth/login` (or use the "Authorize" button in Swagger)
- **Default Credentials:**
  - Username: `admin@capitalzone.com`
  - Password: `password123`
- Copy the returned `access_token`. Put it in the "Authorize" header (`Bearer <access_token>`).

### Step 4: Test Direct Card Ingestion (Idempotency & Fields)
Submit a structured Knowledge Card payload to:
- **Endpoint:** `POST /api/v1/rag/collections/documents/ingest/card`
- **Request Body:**
```json
{
  "card_id": "d3b07384-d113-4e44-b040-cf1ff7e5a872",
  "content": "This is a high confidentiality Lesson Learned regarding database migration index tuning. Ensure that Qdrant payload indexes are generated correctly.",
  "type": "Lesson",
  "status": "draft",
  "version": 1,
  "area": "Engineering",
  "project": "Migration",
  "tags": ["postgres", "qdrant"],
  "confidence": "high",
  "confidentiality": "high",
  "owner": "admin@capitalzone.com",
  "language": "en",
  "source_pointer": "s3://archive/migration_report.pdf",
  "source_checksum": "sha256-abcdef123456",
  "source_created_at": "2026-08-01T12:00:00Z",
  "document_id": "e4f50682-1234-4bc6-88ab-f11ff7a5d333"
}
```
**Verify:**
1. The endpoint returns `status: "done"`.
2. Re-send the exact request. Verify that the request completes successfully without throwing duplicate constraint exceptions (verifying **idempotency**).

### Step 5: Verify Dynamic Security & Access Filters
Search the collection using:
- **Endpoint:** `POST /api/v1/rag/search`
- **Request Body:**
```json
{
  "collection_name": "documents",
  "query": "database migration index tuning",
  "limit": 4
}
```
**Verify Boundaries:**
1. **Status Gate:** By default, searching with a viewer/member role will NOT return the card because its status is `"draft"`.
2. **Override Status Gate:** Re-run the query as an `admin` or `owner` role while passing `"status": ["draft"]` in the query payload. Verify that the card is now retrieved correctly.
3. **Tenant Isolation:** Submit a query using a header or token associated with a different tenant. Verify that search returns empty results, enforcing deny-by-default isolation.

### Step 6: Verify Auditing Decision Logs
Check the PostgreSQL database to confirm audit logs are generated:
- Query `app_admin_audit_logs` table.
- Verify that a log entry with `action: "rag_retrieval_search"` or `action: "rag_retrieval_query"` was created, containing the applied status filters and result counts.

### Step 7: Run CLI RAGAS Accuracy Evaluation
Evaluate the retrieval accuracy of the pipeline using the golden questions:
```bash
uv run rag_pipeline cmd rag-evaluate --collection documents
```
Verify that RAGAS metrics calculate successfully and output `evaluation_report.json` in the root backend folder.
