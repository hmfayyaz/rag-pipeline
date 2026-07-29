# 02. Required Environment Variables

This document lists the local environment variables for the **FastAPI backend** inside the `.env` file. 

To run the local stack on macOS with local Ollama, copy this configuration to your local `backend/.env`.

---

## 1. Environment Config Matrix (Local Execution)

| Variable Name | Value | Purpose |
| :--- | :--- | :--- |
| **`PROJECT_NAME`** | `rag_pipeline` | Identifier for logs and schemas. |
| **`DEBUG`** | `true` | Enables verbose stack traces and logging. |
| **`ENVIRONMENT`** | `local` | Tells the system to look for local developer settings. |
| **`TIMEZONE`** | `UTC` | Timezone context for database timestamp audits. |
| **`SECRET_KEY`** | `e0f76de45d7a6411516e87a2a01344400e9cf7685600d866a1bc683e390c5211` | HMAC secret for JWT signing (generate via `openssl rand -hex 32`). |
| **`ALGORITHM`** | `HS256` | JWT signature algorithm. |
| **`ACCESS_TOKEN_EXPIRE_MINUTES`** | `10080` | Access token lifespan (7 days). |

---

## 2. Databases & Vector Stores

Depending on where you run the FastAPI backend server (inside Docker or directly on the Host macOS), configuration hosts must shift:

### Option A: Running FastAPI Backend directly on Host macOS (Recommended)
This uses the lowest RAM footprint. Run services in Docker and the python code on the host.

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=rag_pipeline

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=

# Ollama Endpoint (Host Local)
OLLAMA_BASE_URL=http://localhost:11434
```

### Option B: Running FastAPI Backend inside Docker Compose
Useful if you want pure containerization, but draws more RAM overhead (~500 MB extra).

```bash
# PostgreSQL (points to database container inside bridge network)
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=rag_pipeline

# Qdrant (points to qdrant container)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=

# Ollama Endpoint (Resolves back to host macOS network gateway)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 3. RAG, Parsing, and AI Models (Ollama)

```bash
# RAG Params
RAG_DEFAULT_COLLECTION=documents
RAG_TOP_K=5
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=50
RAG_CHUNKING_STRATEGY=recursive
RAG_HYBRID_SEARCH=false

# PDF and document parser
PDF_PARSER=pymupdf
CHAT_PDF_PARSER=pymupdf

# Local AI Models
AI_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text

# Email configurations (Write to console to avoid external API calls)
EMAIL_PROVIDER=log
EMAIL_FROM=noreply@rag-pipeline.com
EMAIL_FROM_NAME=RAG-Pipeline
```
