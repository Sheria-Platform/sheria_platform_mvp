#!/bin/bash
# =============================================================================
# deploy/local_dev/scripts/entrypoint.sh
# Sheria Platform — Generic Ollama Node Startup + Model Pull
# =============================================================================
# Usage (set via docker-compose.yml environment):
#   MODELS_TO_PULL="qwen3:8b"                    # single model
#   MODELS_TO_PULL="nomic-embed-text,qwen2.5:3b" # comma-separated list
#
# What this does:
#   1. Start Ollama server in background
#   2. Wait for the REST API to be ready
#   3. Pull each model listed in MODELS_TO_PULL
#   4. Warm up: load each model into GPU/CPU memory immediately
#   5. Keep container alive (wait for background Ollama process)
# =============================================================================

set -e

echo "[entrypoint] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for the Ollama REST API to accept connections
echo "[entrypoint] Waiting for Ollama API to be ready..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "[entrypoint] Ollama API is ready."

# Pull and warm up each model listed in MODELS_TO_PULL
# Accepts comma-separated or space-separated list (e.g. "qwen3:8b,nomic-embed-text")
if [ -n "${MODELS_TO_PULL:-}" ]; then
    for model in $(echo "${MODELS_TO_PULL}" | tr ',' ' '); do
        echo "[entrypoint] Pulling model: $model"
        ollama pull "$model"

        echo "[entrypoint] Warming up model: $model (loading into memory)"
        # Send an empty generate request with keep_alive=-1 to pin the model
        # in memory until the container stops. This eliminates cold-start
        # latency on the first real request.
        curl -sf http://localhost:11434/api/generate \
            -H "Content-Type: application/json" \
            -d "{\"model\":\"${model}\",\"keep_alive\":-1}" \
            > /dev/null || true

        echo "[entrypoint] Model ready: $model"
    done
else
    echo "[entrypoint] MODELS_TO_PULL is not set — skipping model pull."
fi

echo "[entrypoint] All models loaded. Node is ready."

# Keep container alive until Ollama server exits
wait $OLLAMA_PID
