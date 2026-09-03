# RAG Pipeline Execution & Swagger UI Guide

A complete, simple, and detailed guide on **how to start the application** and execute the **5-step RAG flow** directly from the Swagger UI at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Part 1: How to Run the Application

Follow these quick terminal commands to run the backend and its services from scratch:

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/) installed and running.
- [uv](https://docs.astral.sh/uv/) Python package manager installed.

---

### 2. Step-by-Step Server Setup

#### Step 1: Start Infrastructure Services (PostgreSQL & Qdrant)
From the root of the project repository, start the database and vector store containers in the background:
```bash
docker compose up db qdrant -d
```
> This starts:
> - **PostgreSQL** database on port `5433` (container port 5432)
> - **Qdrant Vector DB** on port `6333`

To verify they are running:
```bash
docker ps
```

---

#### Step 2: Backend Environment Setup
Navigate into the `backend` directory:
```bash
cd backend
```
Make sure your `.env` file exists. If you haven't created it yet, copy `.env.example`:
```bash
cp .env.example .env
```
Ensure your `.env` has:
- `POSTGRES_PORT=5433`
- `QDRANT_PORT=6333`
- Your `GROQ_API_KEY` (or `OPENAI_API_KEY`) configured for LLM answers.

Install project dependencies:
```bash
uv sync --dev
```

---

#### Step 3: Run Database Migrations
Create and apply all database tables in PostgreSQL:
```bash
uv run alembic upgrade head
```

---

#### Step 4: Seed Database with Default Users
Populate the database with sample tenant users and the main admin:
```bash
uv run rag_pipeline cmd seed
```
> **Default Admin Account Created:**
> - **Email:** `admin@example.com`
> - **Password:** `password123`

---

#### Step 5: Start the FastAPI Backend Server
Start the live-reloading dev server:
```bash
uv run uvicorn app.main:app --reload --port 8000
```
Open your browser and navigate to:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## Part 2: Swagger Authentication (No Copy-Pasting Required)

In Swagger UI, you do **not** need to manually copy or paste JWT tokens:

1. Open **[http://localhost:8000/docs](http://localhost:8000/docs)** in your browser.
2. At the top right of the page, click the green **Authorize** button (with the lock icon 🔓).
3. In the popup window:
   - **Username:** `admin@example.com`
   - **Password:** `password123`
4. Click **Authorize**, then click **Close**.

> Swagger UI is now authorized. Every endpoint you test using the **Try it out** button will automatically include your Bearer token!

---

## Part 3: The 5-Step RAG Execution Flow in Swagger

Follow these 5 steps in Swagger UI under the **`rag`** section:

```
Step 1: POST /api/v1/rag/collections/{name}   (Create Collection)
   │
   ▼
Step 2: POST /api/v1/rag/collections/{name}/ingest (Upload File / Book)
   │    OR: /ingest/card (Direct Text Ingestion)
   │
   ▼
Step 3: GET  /api/v1/rag/collections/{name}/documents (Verify Ingestion)
   │
   ▼
Step 4: POST /api/v1/rag/query                (Ask Question ➔ Get AI Answer)
   │
   ▼
Step 5: POST /api/v1/rag/search               (Optional: Raw Vector Search)
```

---

### Step 1: Create a Collection

Before uploading a book or document, create a collection in Qdrant.

- **Section:** `rag`
- **Endpoint:** `POST /api/v1/rag/collections/{name}`
- **Click:** **Try it out**
- **Parameters:**
  - `name`: `documents`
- **Click:** **Execute**

#### Expected Response (Code 201):
```json
{
  "message": "Collection 'documents' created successfully."
}
```

---

### Step 2: Upload Your File or Book

You have two ways to upload knowledge into this collection:

#### Option A: Upload a File / Book (`.pdf`, `.txt`, `.docx`, `.md`)
- **Section:** `rag`
- **Endpoint:** `POST /api/v1/rag/collections/{name}/ingest`
- **Click:** **Try it out**
- **Fill in the fields:**
  - `name`: `documents`
  - `file`: Click **Choose File** and select your book or document (e.g. `book.pdf` or `notes.txt`)
  - `replace`: `false`
  - `confidentiality`: `public`
  - `card_status`: `approved`
  - *(Leave other optional fields empty)*
- **Click:** **Execute**

#### Expected Response (Code 202):
```json
{
  "id": "e7b1a234-5678-4a1b-9c0d-1e2f3a4b5c6d",
  "status": "processing",
  "filename": "book.pdf",
  "collection": "documents",
  "message": "File accepted. Processing in background."
}
```

---

#### Option B: Direct Text Ingestion (Instant Knowledge Card)
If you want to paste text or a chapter directly without a file:
- **Section:** `rag`
- **Endpoint:** `POST /api/v1/rag/collections/{name}/ingest/card`
- **Click:** **Try it out**
- **Parameters:**
  - `name`: `documents`
- **Request Body:**
```json
{
  "card_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "content": "The Antigravity RAG Pipeline uses FastAPI and Qdrant vector database. The capital of Australia is Canberra.",
  "type": "Lesson",
  "status": "approved",
  "version": 1,
  "confidence": "high",
  "confidentiality": "public",
  "owner": "admin@example.com",
  "language": "en"
}
```
- **Click:** **Execute**

#### Expected Response (Code 201):
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "done",
  "filename": "card_3fa85f64-5717-4562-b3fc-2c963f66afa6.txt",
  "collection": "documents",
  "message": "Card successfully ingested."
}
```

---

### Step 3: Verify Ingested Documents

Confirm that your document is stored and processed into the collection.

- **Section:** `rag`
- **Endpoint:** `GET /api/v1/rag/collections/{name}/documents`
- **Click:** **Try it out**
- **Parameters:**
  - `name`: `documents`
- **Click:** **Execute**

#### Expected Response (Code 200):
```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "filename": "card_3fa85f64-5717-4562-b3fc-2c963f66afa6.txt",
      "chunk_count": 1
    }
  ],
  "total": 1
}
```

---

### Step 4: Ask Questions & Get AI-Generated Answers

This is the main RAG querying endpoint. It searches Qdrant for the most relevant chunks from your uploaded document, passes them to the LLM (Groq / Qwen), and returns an answer strictly grounded in your document with citations.

- **Section:** `rag`
- **Endpoint:** `POST /api/v1/rag/query`
- **Click:** **Try it out**
- **Request Body:**
```json
{
  "collection_name": "documents",
  "query": "What vector database is used?",
  "limit": 3
}
```
- **Click:** **Execute**

#### Expected Response (Code 200):
```json
{
  "answer": "Based on the provided document, the Antigravity RAG Pipeline uses Qdrant as the vector database.",
  "citations": [
    {
      "content": "The Antigravity RAG Pipeline uses FastAPI and Qdrant vector database...",
      "score": 1.0,
      "filename": "card_3fa85f64-5717-4562-b3fc-2c963f66afa6.txt",
      "page_num": 1
    }
  ]
}
```

---

### Step 5 (Optional): Test Raw Vector Search

If you want to view the raw vector similarity scores and text chunks without calling the LLM:

- **Section:** `rag`
- **Endpoint:** `POST /api/v1/rag/search`
- **Click:** **Try it out**
- **Request Body:**
```json
{
  "collection_name": "documents",
  "query": "vector database",
  "limit": 3
}
```
- **Click:** **Execute**
- **Response:** Returns the top matching text snippets with cosine similarity scores.

---

## Part 4: Seeded Users Reference

When you run `uv run rag_pipeline cmd seed`, the following users are created in your local database:

| Email | Password | Global Role | Purpose |
| :--- | :--- | :--- | :--- |
| **`admin@example.com`** | `password123` | **`admin` (App Admin)** | **Use this for Swagger UI** (Has full access to all `/rag` endpoints) |
| `owner@tenant-a.com` | `password123` | `user` | Tenant A Owner |
| `admin@tenant-a.com` | `password123` | `user` | Tenant A Admin |
| `member@tenant-a.com` | `password123` | `user` | Tenant A Member |
| `viewer@tenant-a.com` | `password123` | `user` | Tenant A Viewer |

---

## Part 5: Troubleshooting & Key Tips

1. **"Failed to fetch" Error in Swagger:**
   - The Uvicorn server is not running. Start it with:
     ```bash
     cd backend && uv run uvicorn app.main:app --reload --port 8000
     ```
2. **Always Authorize First:** Click the top-right green **Authorize** button with `admin@example.com` / `password123`.
3. **Use the Same Collection Name:** If you create a collection named `documents`, use `collection_name: "documents"` when uploading and querying.
4. **Card Status:** When uploading or ingesting, keep `card_status: "approved"` and `confidentiality: "public"` so the retrieval engine doesn't filter them out.
