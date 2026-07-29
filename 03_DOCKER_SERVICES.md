# 03. Docker Services Directory & Resource Estimation

This document defines the minimum Docker and host services required to spin up the local RAG pipeline, including resource limits, image configurations, and Apple Silicon compatibility assessments.

---

## 1. Services Profile Table

To run on an 8 GB RAM M2 Mac, we **isolate only the core databases in Docker** and run the application and model server natively on the host machine.

| Service Name | Running Environment | Docker Image / Source | M2 Native arm64? | Est. Idle RAM | Est. Active RAM | Est. Disk Space |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`db` (PostgreSQL)** | Docker Compose | `postgres:16-alpine` | Yes | ~50 MB | ~120 MB | ~230 MB |
| **`qdrant` (Vector Store)**| Docker Compose | `qdrant/qdrant:v1.18.3` | Yes | ~80 MB | ~200 MB | ~160 MB |
| **`ollama` (AI Engine)** | Host macOS (Native) | [ollama.com](https://ollama.com) | Yes (Metal GPU) | ~50 MB | ~5.1 GB | ~5.0 GB |
| **`app` (FastAPI backend)**| Host macOS (Native) | Local python environment | Yes | ~80 MB | ~150 MB | ~400 MB |

---

## 2. Docker Images to be Downloaded

Executing the minimal startup downloads only two lightweight official images:

1. **`postgres:16-alpine`**
   - Size: ~90 MB compressed, ~230 MB extracted.
   - Architecture: Native arm64 available.
2. **`qdrant/qdrant:v1.18.3`**
   - Size: ~60 MB compressed, ~160 MB extracted.
   - Architecture: Native arm64 available.

*Total Docker Download Overhead:* **~150 MB** (Extremely lightweight).

---

## 3. Ignored / Disabled Services (Zero RAM Overhead)

To protect the 8 GB RAM threshold, the following generated services are **excluded/disabled** from running:

* **Next.js Frontend Container (`frontend`):** Saves **~300 MB RAM** and **~600 MB Disk**. (Admin commands and RAG API operations can be tested via CLI or FastAPI Swagger UI at `http://localhost:8000/docs`).
* **Redis Cache (`redis`):** Saves **~50 MB RAM** and **~30 MB Disk**.
* **Celery Background Worker & Flower (`celery_worker`, `celery_beat`, `flower`):** Saves **~400 MB RAM** and **~500 MB Disk**.
* **Milvus standalones (`etcd`, `minio`, `milvus`):** Saves **~1.5 GB RAM** and **~1.2 GB Disk** (extremely heavy).
* **Nginx Reverse Proxy (`nginx`):** Saves **~30 MB RAM** and **~20 MB Disk**.
