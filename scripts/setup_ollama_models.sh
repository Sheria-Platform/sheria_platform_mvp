#!/usr/bin/env bash
# scripts/setup_ollama_models.sh
#
# Pull all Ollama models required by the Sheria Platform:
#   - LLM model     : used by the FastAPI agentic RAG service (planner + responder)
#   - Embedding model: used by the FastAPI service and the ingestion pipeline
#
# Usage (inside a running Ollama container):
#   docker exec -it sheria-ollama bash /scripts/setup_ollama_models.sh
#
# Usage (against a remote host):
#   OLLAMA_HOST=http://192.168.214.22:11435 bash scripts/setup_ollama_models.sh
#
# Environment variables (all optional — defaults match docker-compose/env.example):
#   OLLAMA_HOST            Base URL of Ollama  (default: http://localhost:11434)
#   OLLAMA_LLM_MODEL       LLM model to pull   (default: llama3.3)
#   OLLAMA_EMBEDDING_MODEL Embed model to pull  (default: nomic-embed-text)

set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_LLM_MODEL="${OLLAMA_LLM_MODEL:-llama3.3}"
OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

echo "========================================"
echo "  Sheria Platform — Ollama Model Setup"
echo "========================================"
echo "  Host  : ${OLLAMA_HOST}"
echo "  LLM   : ${OLLAMA_LLM_MODEL}"
echo "  Embed : ${OLLAMA_EMBEDDING_MODEL}"
echo "========================================"

# ── Wait for Ollama to be ready ──────────────────────────────────────────────
echo ""
echo "[1/3] Waiting for Ollama to be ready..."
MAX_WAIT=120
ELAPSED=0
until curl -sf "${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; do
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "ERROR: Ollama did not become ready within ${MAX_WAIT}s. Aborting."
        exit 1
    fi
    echo "  Ollama not ready yet, retrying in 5s... (${ELAPSED}s elapsed)"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done
echo "  Ollama is ready."

# ── Pull LLM model ────────────────────────────────────────────────────────────
echo ""
echo "[2/3] Pulling LLM model: ${OLLAMA_LLM_MODEL} ..."
OLLAMA_HOST="${OLLAMA_HOST}" ollama pull "${OLLAMA_LLM_MODEL}"
echo "  LLM model pulled successfully."

# ── Pull Embedding model ──────────────────────────────────────────────────────
echo ""
echo "[3/3] Pulling embedding model: ${OLLAMA_EMBEDDING_MODEL} ..."
OLLAMA_HOST="${OLLAMA_HOST}" ollama pull "${OLLAMA_EMBEDDING_MODEL}"
echo "  Embedding model pulled successfully."

# ── Verify models are present ─────────────────────────────────────────────────
echo ""
echo "Verifying installed models..."
INSTALLED=$(curl -sf "${OLLAMA_HOST}/api/tags" | python3 -c \
    "import sys, json; [print(' •', m['name']) for m in json.load(sys.stdin).get('models', [])]" \
    2>/dev/null || echo "  (could not parse model list)")
echo "${INSTALLED}"

echo ""
echo "Setup complete! The following models are ready:"
echo "  LLM       : ${OLLAMA_LLM_MODEL}"
echo "  Embeddings: ${OLLAMA_EMBEDDING_MODEL}"
echo ""
echo "Start the full stack with:  docker compose up -d"
echo "========================================"
