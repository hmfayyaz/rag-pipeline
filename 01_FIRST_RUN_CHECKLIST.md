# 01. First Run Checklist

This checklist prepares a local environment on a **macOS Apple Silicon M2 (8 GB RAM)** machine to run the RAG pipeline baseline project. 

---

## 1. System Pre-Requisites & Compatibility

- [ ] **Docker Desktop Installed & Running:**
  - Verify version: `docker --version` (Ensure version 24+).
  - Verify Docker Desktop is configured for **Apple Silicon** (Uses Virtualization framework, `Use Rosetta for x86/amd64 emulation on Apple Silicon` option is checked).
- [ ] **Local Ollama Installed (Host Machine):**
  - **CRITICAL:** Do NOT run Ollama inside Docker. On an 8 GB RAM M2 Mac, running Ollama in Docker consumes excessive memory and disables native Apple Metal GPU acceleration. Ollama must run natively on the macOS host.
  - Download from: [ollama.com](https://ollama.com).
  - Run model warmup: `ollama run llama3` and `ollama run nomic-embed-text` (or `mxbai-embed-large`).
- [ ] **Python 3.12 & `uv` Tooling:**
  - Verify installation: `python3 --version` and `uv --version`.
- [ ] **Bun (or Node.js) installed:**
  - (Only if Next.js frontend is run, but since frontend is out-of-scope for the final project, this can be skipped. However, for baseline verify, we focus solely on the FastAPI backend).

---

## 2. Port Conflict Checks

Ensure that no local processes are already running on the ports required by our local stack. If any port is in use, stop the service before starting.

Run these checks in terminal:
* **PostgreSQL (Port 5432):** `lsof -i :5432` (Stop any local brew-installed PostgreSQL server).
* **Qdrant (Port 6333):** `lsof -i :6333`
* **FastAPI Backend (Port 8000):** `lsof -i :8000`
* **Ollama (Port 11434):** `lsof -i :11434` (Should be running natively on the host).

---

## 3. Apple Silicon (M2 arm64) Verification

Confirming target images are multi-arch (compatible with Apple Silicon native arm64):
* **PostgreSQL 16 Alpine (`postgres:16-alpine`):** Native arm64 image available.
* **Qdrant (`qdrant/qdrant:v1.18.3`):** Native arm64 image available.
* **FastAPI Backend:** Built locally from `backend/Dockerfile` based on `python:3.12-slim` (compatible with arm64).

---

## 4. RAM & Disk Blockers on 8 GB RAM M2

On 8 GB RAM, running multiple containers alongside Ollama models will lead to swap memory paging. Keep these rules:
1. **Reduce Docker VM Memory Limit:** Set Docker Desktop RAM allocation to **2 GB or 3 GB** maximum. This leaves 5-6 GB for macOS and Ollama to load model weights natively.
2. **Disable Unused Containers:** Stop all containers except `db` (PostgreSQL) and `qdrant`. Disable Next.js, Celery, flower, Redis, etc.
3. **Host Database Access:** Ensure the backend `DATABASE_URL` uses `localhost` instead of the Docker network aliases if you run the FastAPI app directly on the host (highly recommended to save RAM).
