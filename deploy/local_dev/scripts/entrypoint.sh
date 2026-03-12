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
#   3. Pull each model listed in MODELS_TO_PULL (with retry on failure)
#   4. Warm up: load each model into GPU/CPU memory immediately
#   5. Keep container alive (wait for background Ollama process)
# =============================================================================

# No set -e: a failed pull must not crash the container and kill its DNS alias.
# Errors are handled explicitly below so model-puller is never left polling a
# dead node forever.

echo "[entrypoint] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for the Ollama REST API to accept connections
echo "[entrypoint] Waiting for Ollama API to be ready..."
until curl -sf --max-time 5 http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "[entrypoint] Ollama API is ready."

# Pull and warm up each model listed in MODELS_TO_PULL
# Accepts comma-separated or space-separated list (e.g. "qwen3:8b,nomic-embed-text")
if [ -n "${MODELS_TO_PULL:-}" ]; then
    for model in $(echo "${MODELS_TO_PULL}" | tr ',' ' '); do
        echo "[entrypoint] Pulling model: $model"

        # Retry loop — transient network errors must not crash the container.
        PULL_ATTEMPTS=0
        PULL_MAX=5
        PULL_OK=0
        while [ "$PULL_ATTEMPTS" -lt "$PULL_MAX" ]; do
            if ollama pull "$model"; then
                PULL_OK=1
                break
            fi
            PULL_ATTEMPTS=$((PULL_ATTEMPTS + 1))
            echo "[entrypoint] Pull failed (attempt $PULL_ATTEMPTS/$PULL_MAX). Retrying in 15s..."
            sleep 15
        done

        if [ "$PULL_OK" -eq 0 ]; then
            echo "[entrypoint] ERROR: could not pull $model after $PULL_MAX attempts. Aborting."
            kill "$OLLAMA_PID" 2>/dev/null
            exit 1
        fi

        echo "[entrypoint] Warming up model: $model (loading into memory)"
        # --max-time 60: prevents the streaming generate request from hanging
        # the entrypoint forever if Ollama does not close the connection.
        # || true: warmup failure is non-fatal; the model is already pulled and
        # will load on first real request.
        curl -sf --max-time 60 http://localhost:11434/api/generate \
            -H "Content-Type: application/json" \
            -d "{\"model\":\"${model}\",\"keep_alive\":-1}" \
            > /dev/null \
            || echo "[entrypoint] Warmup request failed (non-fatal, continuing)"

        echo "[entrypoint] Model ready: $model"
    done
else
    echo "[entrypoint] MODELS_TO_PULL is not set — skipping model pull."
fi

echo "[entrypoint] All models loaded. Node is ready."

# Keep container alive until Ollama server exits
wait "$OLLAMA_PID"
