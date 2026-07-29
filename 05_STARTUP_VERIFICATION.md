# 05. Startup Verification Report

This report outlines the verified architectural pathways, file structures, and startup commands of the **full-stack-ai-agent-template** repository based on direct inspection of the codebase.

---

## 1. Verified Directory & File Locations

* **1. Backend Entry Point (Actual File Path):**
  * Located in the template folder at: `template/{{cookiecutter.project_slug}}/backend/app/main.py`.
* **2. Docker Compose Files (Actual File Paths):**
  * Development Stack: `template/{{cookiecutter.project_slug}}/docker-compose.dev.yml`
  * Baseline Stack: `template/{{cookiecutter.project_slug}}/docker-compose.yml`
  * Production Stack: `template/{{cookiecutter.project_slug}}/docker-compose.prod.yml`
  * Frontend Stack: `template/{{cookiecutter.project_slug}}/docker-compose.frontend.yml`
* **3. Docker Compose File to Use First:**
  * **`docker-compose.dev.yml`** (Used by the local Makefile `make dev` target to mount backend folders with live-reload volume flags).
* **4. Existing Services in Docker Compose:**
  * The template's `docker-compose.dev.yml` lists the following services:
    * `app` (FastAPI backend service)
    * `db` (PostgreSQL database service)
    * `redis` (Redis cache - optional)
    * `etcd` (Milvus coordinator dependency - optional)
    * `minio` (Milvus storage dependency - optional)
    * `milvus` (Milvus standalone vector store - optional)
    * `qdrant` (Qdrant vector store - optional)
    * `celery_worker` (Celery background worker - optional)
    * `celery_beat` (Celery scheduler - optional)
    * `flower` (Celery dashboard - optional)
    * `taskiq_worker` (Taskiq background worker - optional)
    * `taskiq_scheduler` (Taskiq scheduler - optional)
    * `prefect-server` (Prefect dashboard - optional)
    * `prefect-runner` (Prefect worker - optional)
* **5. Existing `.env` Templates:**
  * Backend: `template/{{cookiecutter.project_slug}}/backend/.env.example`
  * Frontend: `template/{{cookiecutter.project_slug}}/frontend/.env.example`
  * *(No active `.env` file exists until copied).*

---

## 2. Command Log & Technical Configurations

* **6. First Execution Command (Documentation):**
  * The root `README.md` and the generated template `README.md` command is:
    ```bash
    make bootstrap
    ```
    *(This target executes `make dev` and `make seed` sequentially to start the stack and seed the admin user).*
* **7. Target README to Follow:**
  * **`template/{{cookiecutter.project_slug}}/README.md`** should be followed as it contains the specific configuration instructions for the generated backend application runtime.
* **8. Python Package Manager:**
  * **`uv`** is the package manager used (verified by the root `uv.lock` and the Makefile targets using `uv sync` and `uv run`).
* **9. Backend Startup Command:**
  * Via Docker Compose: `make dev` (starts the `app` container).
  * Via Host machine: `make run` (runs: `uv run --directory backend {{ cookiecutter.project_slug }} server run --reload`).
* **10. Database Migration Command:**
  * `make db-upgrade` (runs: `uv run --directory backend {{ cookiecutter.project_slug }} db upgrade`).
* **11. Seeding / Create Admin User Command:**
  * Via Docker Compose: `make seed` (seeds the default `admin@example.com` credentials).
  * Via Host machine: `make create-admin` (runs: `uv run --directory backend {{ cookiecutter.project_slug }} user create-admin`).

---

## 3. Real-World Execution Blockers

Before running the project locally, the following hard blockers must be resolved:

1. **Un-rendered Templates (Jinja2 Blocks):**
   * The files inside the `template/` folder contain Cookiecutter syntax (like `{{ cookiecutter.project_slug }}`). Executing them directly will throw syntax and import errors. The project must first be scaffolded using the `fastapi-fullstack` CLI tool to generate the concrete directories.
2. **Missing `.env` configuration file:**
   * The backend will crash on start due to missing Pydantic-settings dependencies if no `.env` file is present in the `backend/` directory. Copying `.env.example` to `.env` is mandatory.
3. **Local Ollama Host Availability:**
   * During startup, the FastAPI server's lifespan tries to establish connection and run `warmup()` on the configured embeddings/chat clients. If Ollama is not running on port 11434, the server will error out on boot.
4. **Port Conflicts on Port 5432 or 6333:**
   * If a PostgreSQL or Qdrant server is running on the host machine, launching Docker Compose will fail with port binding errors. Existing host databases must be stopped first.
5. **Missing Python Virtualenv Setup:**
   * Running `uv run` commands directly without running `uv sync` first will fail with module resolution/import errors.
