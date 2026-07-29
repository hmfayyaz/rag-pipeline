# Project Development Requirements Report

This report analyzes the **Full-Stack AI Agent Template** repository and its generated output configurations to establish runtime, system, and service requirements for local development.

---

### 1. Python Version Required
* **Generator CLI Tool:** Requires **Python >= 3.11** (tested on `3.11` and `3.12` as defined in the root `pyproject.toml`).
* **Generated Backend:** Defaults to **Python 3.12** (configurable down to `3.11` during setup).

### 2. Dependency Management System
* The project uses **`pyproject.toml`** (PEP 518/621) and **`uv`** (Astral's fast package installer and resolver) for python dependencies. It ships with `uv.lock` lockfiles for strict resolution.
* Next.js frontend (if enabled) uses **`bun`** (recommended) or standard package managers like `npm`/`pnpm`.

### 3. Docker Usage in Development vs. Deployment
* **Development:** Docker is highly recommended for running background services (PostgreSQL, Redis, Milvus/Qdrant) via `docker-compose.dev.yml`. The application servers (FastAPI/Next.js) can run inside Docker or directly on the host OS.
* **Deployment:** Docker is standard for packaging the backend (production multi-stage builds via `docker-compose.prod.yml` or Kubernetes manifests).

### 4. Mandatory Services for Local Development
If running the default generated setup, the following are mandatory:
1. **PostgreSQL 16:** Required for database storage, migrations (Alembic), JWT sessions, and user management.
2. **Redis 7:** Required if background tasks (Celery/Taskiq/Arq) or caching are enabled.
3. **LLM API Credentials:** (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) unless local offline models are configured.

### 5. Optional Services
Depending on the CLI choices made during generation:
* **Next.js Frontend:** (Optional) Can run backend-only.
* **Redis:** Optional if background tasks and caching are disabled.
* **Milvus / Qdrant / ChromaDB:** Optional vector databases (only the one selected for RAG is required; ChromaDB runs embedded).
* **MinIO and etcd:** Only required if using Milvus Standalone.
* **Flower:** Optional Celery task dashboard.
* **Prefect Server:** Optional if Prefect is chosen over Celery.
* **Sentry / Prometheus / Logfire:** Optional observability suites.

### 6. Dependencies That Can Be Skipped Safely
* **Dev/Doc Tooling:** Virtual environments can skip the `[dependency-groups.dev]` group (`ruff`, `ty`, `pytest`, `pre-commit`) and the `docs` extra (`mkdocs`).
* **Frontend:** The entire `frontend/` directory and node dependency installation (`bun install`) can be ignored if only working on the backend/APIs.
* **Unused AI & Vector Frameworks:** For example, if you use `pydantic_ai`, all `langchain`/`langgraph`/`deepagents` dependencies can be skipped. If RAG is disabled, all vector databases and parser libraries are omitted.

### 7. PostgreSQL Requirement
* **Yes, by default.** User authentication, API key storage, and workspace organization metadata are stored in PostgreSQL using SQLAlchemy or SQLModel. It is required for local testing.

### 8. Redis Requirement
* **Conditional.** Redis is not required for a plain API server. However, it is **mandatory** if using:
  * Background tasks (Celery, Taskiq, or Arq)
  * Server-side caching (`fastapi-cache2`)
  * Redis-backed rate-limiting.

### 9. Ollama Requirement
* **No.** The project defaults to hosted APIs (OpenAI, Anthropic, Google Gemini, OpenRouter). Ollama is only required if you explicitly configure local model hosting.

### 10. Qdrant Requirement
* **No.** Qdrant is only required if you choose it as your RAG vector store. Alternate choices include Milvus, ChromaDB (embedded/no-docker), or `pgvector` (PostgreSQL extension).

### 11. Expected Local AI Models
* By default, it expects **Cloud APIs** (e.g. GPT-4o, Claude 3.5 Sonnet).
* If local components are configured:
  * **Embeddings:** Local `sentence-transformers` model (e.g., `all-MiniLM-L6-v2`).
  * **Rerankers:** Local `cross-encoder` model (e.g., `ms-marco-MiniLM-L-6-v2`).
  * **Ollama (Optional):** Models like `llama3`, `mistral`, or `phi3` can be targeted via OpenAI-compatible endpoints.

### 12. Development Completely Without Docker
* **Yes.** You can run the code without Docker by running `uv run uvicorn app.main:app` and `bun dev` on the host machine. 
* **Requirement:** You must run PostgreSQL (and optionally Redis/Vector stores) locally as host processes or point the backend to external cloud databases (e.g., Supabase, Upstash).

### 13. Startup Commands During Development
* **With Docker (Recommended):**
  ```bash
  make bootstrap   # Run once to start services, apply migrations, and seed DB
  make dev         # Day-to-day command to run services with hot-reload
  ```
* **Without Docker (Local host development):**
  ```bash
  # 1. Install packages
  uv sync
  
  # 2. Run backend
  uv run fastapi-fullstack server run --reload
  
  # 3. Run frontend (in frontend/)
  bun dev
  ```

### 14. Estimated Minimum RAM Required
* **Lightweight Setup** (No Docker / ChromaDB / Local Embeddings): **8 GB RAM**.
* **Standard Docker Setup** (Postgres + Redis + Celery): **8 GB - 16 GB RAM**.
* **Heavyweight Setup** (Docker with Milvus standalone, etcd, MinIO, Next.js): **16 GB RAM** (Milvus standalone on Apple Silicon can draw high load during startup).

### 15. Estimated Minimum Disk Space Required
* **Venv & Project Code:** ~1 GB.
* **Full Docker Cache + Node Modules + Vector Volumes:** **5 GB - 10 GB** (primarily Docker base images and `node_modules` cache).
