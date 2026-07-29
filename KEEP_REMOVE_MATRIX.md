# Keep / Remove Scope Reduction Matrix

This document provides a component-by-component classification matrix for the **rag-pipeline** repository. It lists directories, python dependencies, docker services, modules, and features, classifying them as **KEEP**, **REMOVE**, or **OPTIONAL** under the fixed local RAG stack scope.

---

## 1. Directory / Folder Matrix

| Directory Path | Classification | Technical Rationale / Explanation |
| :--- | :--- | :--- |
| `frontend/` | **REMOVE** | Out of scope. Next.js 15 frontend is not needed for a headless RAG API service. |
| `backend/app/agents/` | **KEEP** | Contains agent interfaces. `langchain_assistant.py` is kept; others are removed. |
| `backend/app/api/` | **KEEP** | Defines API endpoints. `auth.py`, `users.py`, `organizations.py`, `knowledge_bases.py`, `members.py`, `agent.py` routes are kept. |
| `backend/app/clients/` | **REMOVE** | Contains client wrappers for external systems like Stripe. Not required. |
| `backend/app/db/` | **KEEP** | Core database configuration, models, and Alembic database migrations. |
| `backend/app/repositories/` | **KEEP** | Data Access Objects (DAO) for database models (Users, Orgs, Audit Logs). |
| `backend/app/schemas/` | **KEEP** | Pydantic validation schemas for core data types. |
| `backend/app/services/` | **KEEP** | Business logic layer. `rag/`, `user.py`, `organization.py`, `member.py`, `invitation.py`, `health.py`, `session.py` are kept. |
| `backend/app/services/billing/` | **REMOVE** | Code relating to Stripe integration and credit limits is out of scope. |
| `backend/app/services/channels/` | **REMOVE** | Slack and Telegram integration services are out of scope. |
| `backend/app/services/email/` | **REMOVE** | Transactional emails (SMTP/Resend integrations) are replaced by console logging. |
| `backend/app/services/rag/connectors/` | **REMOVE** | Google Drive and AWS S3 connectors are removed (in favor of local file uploads). |
| `backend/app/worker/` | **REMOVE** | Celery/Taskiq worker orchestration configurations. Ingestion will use FastAPI in-process BackgroundTasks. |
| `kubernetes/` | **REMOVE** | Kubernetes manifests are out of scope. Local run relies purely on Docker Compose. |
| `nginx/` | **OPTIONAL** | Reverse proxy configurations. Useful if exposing the app behind Nginx, otherwise ports can be bound directly. |
| `docs/` | **OPTIONAL** | Project documentation. Keep for development guides; remove generated template guides. |

---

## 2. Python Dependency Matrix (`backend/pyproject.toml`)

| Dependency | Classification | Technical Rationale / Explanation |
| :--- | :--- | :--- |
| `fastapi` | **KEEP** | Core web framework for hosting endpoints. |
| `uvicorn[standard]` | **KEEP** | ASGI application server to run the FastAPI app. |
| `pydantic` | **KEEP** | Core data validation and settings library. |
| `sqlalchemy` | **KEEP** | Object-Relational Mapper (ORM) for PostgreSQL database interaction. |
| `asyncpg` | **KEEP** | Async database driver for PostgreSQL connectivity. |
| `psycopg2-binary` | **KEEP** | Synchronous driver required for Alembic migrations. |
| `alembic` | **KEEP** | Database schema migration engine. |
| `pyjwt` | **KEEP** | Core JWT creation and parsing for local user authentication. |
| `bcrypt` | **KEEP** | Required for hashing and verifying user passwords locally. |
| `langchain` | **KEEP** | Core orchestration framework for the local LLM and Qdrant integration. |
| `langchain-community` | **KEEP** | Required to load the `Ollama` and `OllamaEmbeddings` community drivers. |
| `qdrant-client` | **KEEP** | Database client library for connection to local Qdrant. |
| `pymupdf` | **KEEP** | Parsing engine for extracting clean text from PDF documents. |
| `python-docx` | **KEEP** | Parsing engine for Word (.docx) document ingestion. |
| `langchain-text-splitters`| **KEEP** | Text chunking algorithms (e.g., RecursiveCharacterTextSplitter). |
| `rank-bm25` | **KEEP** | Sparse retriever to support hybrid retrieval setups. |
| `ragas` | **KEEP (NEW)** | Added package to evaluate the local RAG pipeline metrics. |
| `pydantic-ai-slim` | **REMOVE** | PydanticAI is out of scope. |
| `deepagents` | **REMOVE** | DeepAgents framework is out of scope. |
| `langgraph` | **REMOVE** | LangGraph framework is out of scope. |
| `pymilvus` | **REMOVE** | Milvus vector store client is out of scope. |
| `chromadb` | **REMOVE** | ChromaDB vector store client is out of scope. |
| `redis` | **REMOVE** | In-memory cache database client is out of scope. |
| `celery` | **REMOVE** | Celery distributed task library is out of scope. |
| `taskiq` | **REMOVE** | Taskiq background task library is out of scope. |
| `stripe` | **REMOVE** | Billing and checkout SDK is out of scope. |
| `boto3` | **REMOVE** | Amazon S3 SDK is out of scope. |
| `google-api-python-client`| **REMOVE** | Google Drive API SDK is out of scope. |
| `aiogram` | **REMOVE** | Telegram Bot SDK is out of scope. |
| `slack-sdk` | **REMOVE** | Slack integration SDK is out of scope. |
| `slowapi` | **REMOVE** | Rate limiting library is out of scope. |
| `logfire` | **REMOVE** | Observability logging suite is out of scope. |

---

## 3. Docker Compose Services Matrix (`docker-compose.yml`)

| Service Name | Classification | Technical Rationale / Explanation |
| :--- | :--- | :--- |
| `app` (FastAPI backend) | **KEEP** | Serves APIs, manages users, coordinates retrieval/ingestion. |
| `db` (Postgres database) | **KEEP** | Persistent store for JWT sessions, RBAC mappings, and audit logs. |
| `qdrant` (Vector store) | **KEEP** | Fast vector database for storing text embeddings and tenant-filtered search. |
| `ollama` (Local LLM runner) | **KEEP (NEW)** | Spawns local AI models (llama3/mistral) and embeddings offline. |
| `restic` (Backup engine) | **KEEP (NEW)** | Runs scheduled encrypted backups of Qdrant and Postgres volumes. |
| `redis` | **REMOVE** | Removed since Celery tasks and caching are disabled. |
| `etcd` / `minio` / `milvus`| **REMOVE** | Removed since Milvus is not used as the vector store. |
| `celery_worker` / `flower` | **REMOVE** | Removed since distributed tasks are replaced by FastAPI native background worker. |
| `taskiq_worker` | **REMOVE** | Removed since Taskiq is disabled. |
| `prefect-server` / `runner` | **REMOVE** | Removed since Prefect is out of scope. |
| `nginx` | **OPTIONAL** | Excluded in local compose unless production-like environment testing is needed. |

---

## 4. Modules & Features Matrix

| Module / Feature | Classification | Technical Rationale / Explanation |
| :--- | :--- | :--- |
| **JWT Authentication** | **KEEP** | Local credentials/token checks (`verify_token` in `security.py`) are kept. |
| **RBAC Policies** | **KEEP** | Role checking dependencies (`RoleChecker`, `RequireOrgRole`) enforce API governance. |
| **tenant_id Isolation** | **KEEP** | Active organization boundaries are enforced by passing the tenant ID header/expression to Qdrant filter queries. |
| **Audit Logs** | **KEEP** | Saves actions to the `AppAdminAuditLog` SQL model for security compliance. |
| **RAGAS Evaluations** | **KEEP (NEW)** | Evaluation script executed locally using LangChain + Ollama models. |
| **Restic Backup Script** | **KEEP (NEW)** | Encrypted volume snapshot script pointing to local host directories. |
| **Document Ingestion** | **KEEP** | Ingests PDF/DOCX files directly via HTTP form payload using `BackgroundTasks`. |
| **Stripe Billing** | **REMOVE** | Plan limits, subscriptions, and payment webhook models are out of scope. |
| **OAuth Registration** | **REMOVE** | Sign-In with Google is disabled; credentials are username/password only. |
| **SMTP / Email Send** | **REMOVE** | Replaced with print-to-console (`email_provider = "log"`) to prevent cloud dependency. |
| **MCP Integrations** | **REMOVE** | Model Context Protocol clients are out of scope. |
| **SaaS LLM fallbacks** | **REMOVE** | System parameters strictly mandate local Ollama configuration. |
