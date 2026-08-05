#!/bin/bash

# Get the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "========================================"
echo "🛑 Stopping RAG Pipeline Services..."
echo "========================================"

# 1. Stop FastAPI server
echo "1. Stopping FastAPI backend server..."
pkill -f uvicorn

# 2. Stop Docker containers
echo "2. Stopping Postgres & Qdrant Docker containers..."
docker-compose down

# 3. Stop Ollama
echo "3. Stopping Ollama app..."
osascript -e 'quit app "Ollama"' 2>/dev/null || pkill -f Ollama

echo "========================================"
echo "✅ All services stopped successfully."
echo "========================================"
