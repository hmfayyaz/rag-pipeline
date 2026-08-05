#!/bin/bash

# Get the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "========================================"
echo "🚀 Starting RAG Pipeline Services..."
echo "========================================"

# 1. Start Docker containers
echo "1. Starting Postgres & Qdrant Docker containers..."
docker-compose up -d

# 2. Start Ollama
echo "2. Launching Ollama app..."
open -a Ollama

# 3. Start FastAPI server
echo "3. Starting FastAPI backend dev server..."
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
