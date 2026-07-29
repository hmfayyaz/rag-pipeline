# System Architecture Map

This document outlines the architectural mapping of the **rag-pipeline** backend application. It details how logical features translate to files, services, database tables, and external integrations in the pruned local system stack.

---

## 1. Overall System Architecture Layout

The application follows a structured layered architecture consisting of the following key tiers:

1. **API Router Layer (`backend/app/api/`):** Defines Fastapi endpoints, route controllers, and HTTP exceptions.
2. **Dependency Injection Layer (`backend/app/api/deps.py`):** Configures resource lifespans, extracts active organization contexts (tenants), validates JWT credentials, and supplies transactional DB sessions.
3. **Service Layer (`backend/app/services/`):** Executes business logic (orchestrating database queries, parsing documents, chunking, retrieving vectors, calling LLMs).
4. **Repository/Data Access Layer (`backend/app/repositories/`):** Abstracts core SQLAlchemy SQL execution queries.
5. **Database Model Layer (`backend/app/db/`):** Outlines primary declarative base schemas and migrations (Alembic).

---

## 2. Core Architecture Map by Feature

Here is the architectural decomposition for every major system capability:

### Authentication
* **1. Entry Point:** `backend/app/api/routes/v1/auth.py`
* **2. Files Involved:**
  * Router: `backend/app/api/routes/v1/auth.py`
  * Security Engine: `backend/app/core/security.py`
  * Dependency Injector: `backend/app/api/deps.py`
  * Service: `backend/app/services/user.py`
  * Repository: `backend/app/repositories/user.py`
* **3. Services Involved:** `UserService`, `UserRepo`
* **4. Database Tables Used:** `users`
* **5. APIs Exposed:**
  * `POST /api/v1/auth/login` (generates access and refresh tokens)
  * `POST /api/v1/auth/refresh` (renews access token via refresh token)
  * `POST /api/v1/auth/register` (registers a new user)
  * `POST /api/v1/auth/logout` (invalidates session token)
* **6. Dependencies Required:** `fastapi`, `pyjwt`, `bcrypt`
* **7. Execution Flow:** Incoming credentials request -> Router -> calls `UserService.authenticate()` -> queries `UserRepo` to fetch user record -> verifies password via `bcrypt` -> returns generated JWT payload.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Core security gating.
* **10. Is this feature required for our fixed project scope?** Yes (JWT Authentication).

### Users
* **1. Entry Point:** `backend/app/api/routes/v1/users.py` (and `admin_users.py`)
* **2. Files Involved:**
  * Router: `backend/app/api/routes/v1/users.py`
  * Database Model: `backend/app/db/models/user.py`
  * Schema Validation: `backend/app/schemas/user.py`
* **3. Services Involved:** `UserService`, `UserRepo`
* **4. Database Tables Used:** `users`
* **5. APIs Exposed:**
  * `GET /api/v1/users/me` (reads profile metadata)
  * `PUT /api/v1/users/me` (updates user credentials)
  * `PUT /api/v1/users/me/password` (modifies password hash)
  * `GET /api/v1/admin/users/` (lists all users - admin only)
* **6. Dependencies Required:** `fastapi`, `pydantic`, `sqlalchemy`
* **7. Execution Flow:** HTTP request includes JWT token -> `get_current_user` dependency verifies signature -> resolves model record -> performs profile query/update -> commits transaction.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Necessary to associate sessions, ownerships, and roles.
* **10. Is this feature required for our fixed project scope?** Yes.

### Organizations (Tenants)
* **1. Entry Point:** `backend/app/api/routes/v1/organizations.py` (plus `members.py` and `invitations.py`)
* **2. Files Involved:**
  * Routers: `organizations.py`, `members.py`, `invitations.py`
  * Database Models: `backend/app/db/models/organization.py`
  * Services: `OrganizationService`, `MemberService`, `InvitationService`
  * Repositories: `backend/app/repositories/organization.py`
* **3. Services Involved:** `OrganizationService`, `MemberService`, `InvitationService`
* **4. Database Tables Used:** `organizations`, `organization_members`, `invitations`
* **5. APIs Exposed:**
  * `GET /api/v1/organizations` (lists user organizations)
  * `POST /api/v1/organizations` (creates new organization)
  * `GET /api/v1/organizations/{org_id}` (retrieves organization details)
  * `POST /api/v1/organizations/{org_id}/invitations` (invites a user to organization)
* **6. Dependencies Required:** `fastapi`, `sqlalchemy`
* **7. Execution Flow:** Client passes `X-Organization-Id` header -> resolved in `get_active_organization` dependency -> validates caller membership -> returns active organization context.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. It establishes the multi-tenant architecture.
* **10. Is this feature required for our fixed project scope?** Yes (tenant_id filtering logic relies on it).

### Role-Based Access Control (RBAC)
* **1. Entry Point:** Dependency annotations in route parameters.
* **2. Files Involved:**
  * Dependency Guards: `backend/app/api/deps.py` (`RoleChecker`, `RequireOrgRole`)
  * Database Models: `backend/app/db/models/user.py` (`UserRole` enum), `backend/app/db/models/organization.py` (`OrgRole` enum)
* **3. Services Involved:** No standalone services. Checks are embedded in route dependency resolution.
* **4. Database Tables Used:** `users`, `organization_members`
* **5. APIs Exposed:** None directly. Acts as filter/guard middleware.
* **6. Dependencies Required:** `fastapi`
* **7. Execution Flow:** Route executes -> checks `Depends(RequireOrgRole("owner", "admin"))` -> queries membership record for user -> raises `AuthorizationError` (403 Forbidden) if user's role is not in the allowed set.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Required for role segregation.
* **10. Is this feature required for our fixed project scope?** Yes (RBAC).

### Document Upload
* **1. Entry Point:** `backend/app/api/routes/v1/files.py` (and `knowledge_bases.py` file uploads)
* **2. Files Involved:**
  * Routers: `backend/app/api/routes/v1/files.py`
  * Services: `backend/app/services/file_upload.py`
* **3. Services Involved:** `FileUploadService`
* **4. Database Tables Used:** `chat_files` (stores uploaded files' locations and metadata)
* **5. APIs Exposed:**
  * `POST /api/v1/files/upload` (accepts multipart/form-data upload)
  * `GET /api/v1/files/{file_id}` (serves file binary)
* **6. Dependencies Required:** `fastapi`, `python-multipart`
* **7. Execution Flow:** Multipart payload sent to API -> `FileUploadService` reads file stream -> saves binary local to `settings.MEDIA_ROOT` -> writes file details to database -> returns file ID.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. It feeds the ingestion pipeline.
* **10. Is this feature required for our fixed project scope?** Yes (Document Ingestion).

### Knowledge Base
* **1. Entry Point:** `backend/app/api/routes/v1/knowledge_bases.py`
* **2. Files Involved:**
  * Router: `backend/app/api/routes/v1/knowledge_bases.py`
  * Model: `backend/app/db/models/knowledge_base.py`
  * Service: `backend/app/services/knowledge_base.py`
* **3. Services Involved:** `KnowledgeBaseService`
* **4. Database Tables Used:** `knowledge_bases`, `rag_documents`
* **5. APIs Exposed:**
  * `GET /api/v1/knowledge-bases` (lists KBs)
  * `POST /api/v1/knowledge-bases` (creates virtual KB collection)
  * `DELETE /api/v1/knowledge-bases/{kb_id}` (deletes KB collection)
* **6. Dependencies Required:** `fastapi`, `sqlalchemy`
* **7. Execution Flow:** Request received -> `KnowledgeBaseService` creates virtual namespace mapping to a Qdrant collection under the active `tenant_id` context.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Necessary to bucket files.
* **10. Is this feature required for our fixed project scope?** Yes.

### Chunking
* **1. Entry Point:** Ingestion worker pipeline (invoked during document ingestion).
* **2. Files Involved:**
  * Service: `backend/app/services/rag/documents.py` (parses and chunks files)
  * Service: `backend/app/services/rag/ingestion.py` (orchestrates ingestion flow)
* **3. Services Involved:** `DocumentProcessor`, `IngestionService`
* **4. Database Tables Used:** None.
* **5. APIs Exposed:** None (Internal service).
* **6. Dependencies Required:** `langchain-text-splitters`, `pymupdf`, `python-docx`
* **7. Execution Flow:** Raw file parsed using PyMuPDF (PDF) or python-docx (DOCX) -> yields string text -> `RecursiveCharacterTextSplitter` segments strings by size and overlap limits -> returns list of `DocumentPageChunk` schemas with page/chunk offsets.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Raw documents are too large for LLM contexts and must be split.
* **10. Is this feature required for our fixed project scope?** Yes (Chunking).

### Embeddings
* **1. Entry Point:** Ingestion pipeline and semantic search retrieval.
* **2. Files Involved:**
  * Service: `backend/app/services/rag/embeddings.py`
  * Driver: `backend/app/services/rag/vectorstore.py` (calls embeddings logic before database upsert)
* **3. Services Involved:** `EmbeddingService`
* **4. Database Tables Used:** None.
* **5. APIs Exposed:** None (Internal service).
* **6. Dependencies Required:** `langchain-community` (Ollama integration) or local `sentence-transformers`.
* **7. Execution Flow:** Raw text chunks list passed to `EmbeddingService` -> triggers a local POST request to Ollama `/api/embeddings` (or executes model locally via CPU/GPU) -> returns float vector arrays.
* **8. External Integrations:** Local Ollama endpoint (`http://ollama:11434`).
* **9. Can this feature be disabled safely?** No. Crucial to translate text to vector space for semantic similarity queries.
* **10. Is this feature required for our fixed project scope?** Yes (Embeddings).

### Qdrant (Vector Database)
* **1. Entry Point:** `backend/app/services/rag/vectorstore.py` (`QdrantVectorStore` implementation)
* **2. Files Involved:**
  * Service: `backend/app/services/rag/vectorstore.py`
  * Config Dependency: `backend/app/api/deps.py` (`get_vectorstore`)
* **3. Services Involved:** `QdrantVectorStore` (inherits `BaseVectorStore`)
* **4. Database Tables Used:** None directly.
* **5. APIs Exposed:** Exposed internally. Handles low-level upsert/search requests.
* **6. Dependencies Required:** `qdrant-client`
* **7. Execution Flow:** `QdrantVectorStore` connects to Qdrant -> inserts/updates documents (`upsert`) or runs vector similarity lookup (`search`) with strict payload metadata filtering (e.g. mapping `parent_doc_id` or `tenant_id`).
* **8. External Integrations:** Qdrant DB service (`http://qdrant:6333`).
* **9. Can this feature be disabled safely?** No.
* **10. Is this feature required for our fixed project scope?** Yes (Qdrant).

### Retrieval
* **1. Entry Point:** Query API endpoints / AI Agent execution hooks.
* **2. Files Involved:**
  * Service: `backend/app/services/rag/retrieval.py`
* **3. Services Involved:** `RetrievalService`
* **4. Database Tables Used:** None.
* **5. APIs Exposed:** Internal service.
* **6. Dependencies Required:** `qdrant-client`, `rank-bm25` (if sparse search is activated)
* **7. Execution Flow:** Input query -> query embedded via `EmbeddingService` -> Qdrant queried for nearest-neighbor match with active `tenant_id` constraint -> output matches returned with distance scores.
* **8. External Integrations:** Qdrant database.
* **9. Can this feature be disabled safely?** No.
* **10. Is this feature required for our fixed project scope?** Yes (RAG Retrieval).

### Chat / RAG
* **1. Entry Point:** `backend/app/api/routes/v1/agent.py`
* **2. Files Involved:**
  * Router: `backend/app/api/routes/v1/agent.py`
  * Service: `backend/app/services/agent_invocation.py`
  * Assistant: `backend/app/agents/langchain_assistant.py`
  * Model: `backend/app/db/models/conversation.py`
  * Service: `backend/app/services/conversation.py`
* **3. Services Involved:** `AgentInvocationService`, `ConversationService`, `RetrievalService`
* **4. Database Tables Used:** `conversations`, `messages`
* **5. APIs Exposed:**
  * `GET /api/v1/agent/chat` (WebSocket connection for RAG chat)
  * `POST /api/v1/agent/chat` (HTTP-based synchronous query execution)
* **6. Dependencies Required:** `fastapi`, `langchain`
* **7. Execution Flow:** Client requests chat -> active tenant resolved -> `RetrievalService` retrieves matching chunks from Qdrant using `tenant_id` filter -> context injected into prompt template -> prompt sent to Ollama LLM (streaming) -> output written to database.
* **8. External Integrations:** Ollama LLM service.
* **9. Can this feature be disabled safely?** No.
* **10. Is this feature required for our fixed project scope?** Yes (Chat / RAG).

### Audit Logs
* **1. Entry Point:** Service transaction calls on sensitive API actions.
* **2. Files Involved:**
  * Database Model: `backend/app/db/models/audit_log.py`
  * Service: `backend/app/services/admin.py`
* **3. Services Involved:** `AdminService`
* **4. Database Tables Used:** `app_admin_audit_logs`
* **5. APIs Exposed:**
  * `GET /api/v1/admin/audit-logs` (admin restricted list endpoint)
* **6. Dependencies Required:** `sqlalchemy`
* **7. Execution Flow:** Administrative action takes place -> caller fetches audit model -> writes actor ID, organization ID, IP, action descriptor, and payload metadata to `app_admin_audit_logs` -> commits database record.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** Yes (if compliance is ignored), but...
* **10. Is this feature required for our fixed project scope?** Yes (Audit Logs).

### Background Tasks
* **1. Entry Point:** FastAPI endpoint action parameters.
* **2. Files Involved:**
  * Router: `backend/app/api/routes/v1/rag.py`
  * Service: `backend/app/services/rag_sync.py`
* **3. Services Involved:** `RAGSyncService`, `IngestionService`
* **4. Database Tables Used:** `rag_documents`
* **5. APIs Exposed:** Core utility triggered on ingestion routes.
* **6. Dependencies Required:** `fastapi`
* **7. Execution Flow:** User sends file upload to KB -> API stores file locally and sets DB document status to `pending` -> schedules `IngestionService.ingest()` via `BackgroundTasks.add_task()` -> immediately returns 202 Accepted to client -> background thread executes text parsing, chunking, embedding, Qdrant upserts, and updates DB status to `completed` or `failed`.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Disabling this blocks request threads during uploads, leading to connection timeouts.
* **10. Is this feature required for our fixed project scope?** Yes (Document Ingestion).

### Docker (Compose)
* **1. Entry Point:** Local shell execution.
* **2. Files Involved:**
  * `docker-compose.dev.yml` (local development composition)
  * `docker-compose.yml` (baseline production composition)
  * `backend/Dockerfile` (backend docker build description)
* **3. Services Involved:** `app`, `db`, `qdrant`, `ollama` (added to compose for offline RAG)
* **4. Database Tables Used:** None.
* **5. APIs Exposed:** Host-to-container port mapping interface (e.g. 8000, 5432, 6333, 11434).
* **6. Dependencies Required:** Docker Engine, Docker Compose CLI.
* **7. Execution Flow:** Developer executes `docker compose up` -> parses YAML structure -> downloads database and vector store images -> builds application image -> links containers in standard network bridge -> launches services in order of dependency declarations.
* **8. External Integrations:** Docker Hub, Quay.io registries.
* **9. Can this feature be disabled safely?** No. Containerization ensures reproducible environment setup.
* **10. Is this feature required for our fixed project scope?** Yes.

### PostgreSQL
* **1. Entry Point:** `backend/app/db/session.py` (initializes connection engine)
* **2. Files Involved:**
  * Session setup: `backend/app/db/session.py`
  * Declarative Base: `backend/app/db/base.py`
  * Database URL Settings: `backend/app/core/config.py`
* **3. Services Involved:** PostgreSQL Database Engine.
* **4. Database Tables Used:** All structured SQL tables.
* **5. APIs Exposed:** Host port 5432 mapped for debugger/CLI database connectivity.
* **6. Dependencies Required:** `sqlalchemy`, `asyncpg`
* **7. Execution Flow:** App starts up -> `create_async_engine()` initializes database connections -> `get_db_session()` yields database sessions per transaction request -> releases connection on completion.
* **8. External Integrations:** None.
* **9. Can this feature be disabled safely?** No. Critical database.
* **10. Is this feature required for our fixed project scope?** Yes.
