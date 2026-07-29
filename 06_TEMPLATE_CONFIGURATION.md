# 06. Template Configuration Plan

This document analyzes the template variables and prompt options defined in `template/cookiecutter.json` and `fastapi_gen/prompts.py` to establish the exact parameters required for generating the **rag-pipeline** application based on our fixed local stack requirements.

---

## 1. Cookiecutter Option Matrix

Here is the classification and recommended choices for each relevant Cookiecutter template variable:

### Variable Name: `project_name`
* **Description:** Name of the generated application directory.
* **Available Choices:** User defined string.
* **Recommended Choice:** `rag_pipeline`
* **Reason:** Aligns with the target repository name (`rag-pipeline`) and generates clean python import directories.

### Variable Name: `database`
* **Description:** Primary SQL database selection.
* **Available Choices:** `postgresql`, `none`
* **Recommended Choice:** `postgresql`
* **Reason:** Mandatory for storing JWT users, session histories, organization memberships (tenants), and system audit logs.

### Variable Name: `orm_type`
* **Description:** The ORM library used for database access.
* **Available Choices:** `sqlalchemy`, `sqlmodel`
* **Recommended Choice:** `sqlalchemy`
* **Reason:** SQLAlchemy 2.0 is fully featured and has native integration support with the audit logging modules.

### Variable Name: `auth`
* **Description:** Enabled authentication endpoints.
* **Available Choices:** `jwt`, `api_key`, `both`, `none`
* **Recommended Choice:** `jwt`
* **Reason:** Matches the JWT Authentication requirement.

### Variable Name: `oauth_provider`
* **Description:** External OAuth social log-ins.
* **Available Choices:** `none`, `google`
* **Recommended Choice:** `none`
* **Reason:** Out of scope. Credentials rely strictly on local email/password JWT tokens.

### Variable Name: `auth_mode`
* **Description:** High-level authentication strategy.
* **Available Choices:** `local` (backend issues/validates JWTs), `delegated` (external IdP validates JWTs)
* **Recommended Choice:** `local`
* **Reason:** Local token management is required to run the pipeline self-contained without cloud Auth0/Clerk dependencies.

### Variable Name: `enable_logfire`
* **Description:** Pydantic Logfire distributed tracing.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `false`
* **Reason:** Out of scope. Logfire is an external cloud platform.

### Variable Name: `background_tasks`
* **Description:** Task broker queue framework.
* **Available Choices:** `celery`, `prefect`, `taskiq`, `arq`, `none`
* **Recommended Choice:** `none`
* **Reason:** Prevents launching resource-heavy broker services (Redis, Celery workers) on an 8 GB RAM machine. Background file ingestion is processed asynchronously via FastAPI's native `BackgroundTasks`.

### Variable Name: `enable_redis`
* **Description:** Spawns a Redis database container.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `false`
* **Reason:** Redis is not needed since background workers and caching are out of scope.

### Variable Name: `enable_websockets`
* **Description:** WebSockets endpoints for conversational chat.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `true`
* **Reason:** Required to host the real-time agent stream at `/agent/chat`.

### Variable Name: `ai_framework`
* **Description:** Core agent orchestration framework.
* **Available Choices:** `pydantic_ai`, `langchain`, `langgraph`, `deepagents`, `pydantic_deep`, `none`
* **Recommended Choice:** `langchain`
* **Reason:** LangChain is mandated by our fixed project scope.

### Variable Name: `llm_provider`
* **Description:** Supported LLM SDK client.
* **Available Choices:** `openai`, `anthropic`, `google`, `openrouter`, `all`
* **Recommended Choice:** `openai`
* **Reason:** Ollama's local server exposes an OpenAI-compatible API interface, allowing standard integration via the OpenAI driver.

### Variable Name: `frontend`
* **Description:** Next.js frontend UI compilation.
* **Available Choices:** `nextjs`, `none`
* **Recommended Choice:** `none`
* **Reason:** Headless RAG pipeline is requested.

### Variable Name: `enable_docker`
* **Description:** Generates Docker Compose configurations.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `true`
* **Reason:** Used to orchestrate local PostgreSQL and Qdrant instances.

### Variable Name: `reverse_proxy`
* **Description:** Web reverse proxy service.
* **Available Choices:** `nginx_external`, `traefik_included`, `traefik_external`, `nginx_included`, `none`
* **Recommended Choice:** `none`
* **Reason:** Exposes PostgreSQL (5432) and Qdrant (6333) ports directly on localhost for easier developer testing.

### Variable Name: `ci_type`
* **Description:** CI/CD script generator.
* **Available Choices:** `github`, `gitlab`, `none`
* **Recommended Choice:** `none`
* **Reason:** Out of scope.

### Variable Name: `enable_rag`
* **Description:** Activates the RAG retrieval pipeline modules.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `true`
* **Reason:** Required for Document Ingestion, PDF parsing, chunking, and semantic lookup.

### Variable Name: `vector_store`
* **Description:** Target database for document embeddings.
* **Available Choices:** `milvus`, `qdrant`, `chromadb`, `pgvector`
* **Recommended Choice:** `qdrant`
* **Reason:** Match target required stack.

### Variable Name: `embedding_provider`
* **Description:** Text embedding calculations provider.
* **Available Choices:** `openai`, `voyage`, `gemini`, `sentence_transformers`
* **Recommended Choice:** `sentence_transformers`
* **Reason:** Generates embeddings locally and offline via HuggingFace models, completely avoiding cloud keys.

### Variable Name: `pdf_parser`
* **Description:** Document parser engine for PDFs.
* **Available Choices:** `pymupdf`, `llamaparse`, `liteparse`, `all`
* **Recommended Choice:** `pymupdf`
* **Reason:** Operates offline, is fast, and has native multi-platform compatibility.

### Variable Name: `enable_teams`
* **Description:** Multi-tenant organization feature.
* **Available Choices:** `true`, `false`
* **Recommended Choice:** `true`
* **Reason:** **MANDATORY.** Provides:
  1. Organization boundaries which map directly to `tenant_id` context.
  2. Organization membership checks to validate tenant isolation rules.
  3. The `AppAdminAuditLog` model code block (which is omitted by Cookiecutter if `enable_teams` is false).

---

## 2. FINAL_COOKIECUTTER_CONFIGURATION

The following exact dictionary must be passed as `cookiecutter.json` or CLI options when scaffolding the project:

```json
{
  "project_name": "rag_pipeline",
  "project_description": "FastAPI Document Ingestion and RAG Pipeline",
  "author_name": "Developer",
  "author_email": "dev@rag-pipeline.local",
  "timezone": "UTC",
  "database": "postgresql",
  "orm_type": "sqlalchemy",
  "auth": "jwt",
  "oauth_provider": "none",
  "auth_mode": "local",
  "enable_session_management": "false",
  "enable_logfire": "false",
  "background_tasks": "none",
  "enable_redis": "false",
  "enable_caching": "false",
  "enable_rate_limiting": "false",
  "enable_pagination": "true",
  "enable_sentry": "false",
  "enable_prometheus": "false",
  "enable_admin_panel": "false",
  "enable_websockets": "true",
  "enable_file_storage": "false",
  "ai_framework": "langchain",
  "llm_provider": "openai",
  "enable_conversation_persistence": "true",
  "enable_langsmith": "false",
  "enable_web_search": "false",
  "enable_web_fetch": "false",
  "enable_charts": "false",
  "enable_code_execution": "false",
  "enable_skills": "false",
  "enable_deep_research": "false",
  "enable_todo": "false",
  "enable_subagents": "false",
  "enable_mcp_client": "false",
  "enable_webhooks": "false",
  "enable_cors": "true",
  "enable_docker": "true",
  "reverse_proxy": "none",
  "ci_type": "none",
  "enable_kubernetes": "false",
  "generate_env": "true",
  "python_version": "3.12",
  "frontend": "none",
  "enable_rag": "true",
  "vector_store": "qdrant",
  "embedding_provider": "sentence_transformers",
  "pdf_parser": "pymupdf",
  "enable_google_drive_ingestion": "false",
  "enable_s3_ingestion": "false",
  "enable_rag_image_description": "false",
  "use_telegram": "false",
  "use_slack": "false",
  "enable_teams": "true",
  "enable_billing": "false",
  "enable_credits_system": "false",
  "enable_marketing_site": "false",
  "tenancy": "multi_org",
  "enable_email": "false"
}
```
