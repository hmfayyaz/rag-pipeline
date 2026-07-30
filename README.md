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
