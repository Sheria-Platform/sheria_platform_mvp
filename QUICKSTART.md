# Sheria Platform — 5-Minute Quick Start Guide

This guide gets the full Sheria Platform stack running on your local machine in under five minutes. By the end you will have all seven infrastructure services running, Ollama loaded with the required models, and a working API you can query.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Docker Engine | 24.0+ | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose | 2.24+ | Bundled with Docker Desktop |
| Python | 3.11 | For running scripts outside Docker |
| RAM | 16 GB | 32 GB recommended when running Ollama with llama3.3 |
| Disk space | 20 GB free | Model weights + Docker images |
| NVIDIA GPU | Optional | Significantly speeds up LLM inference in Ollama |

> **macOS users**: Docker Desktop on Apple Silicon (M-series) runs Ollama efficiently on CPU. Expect ~15-25 tokens/sec for llama3.3.

---

## Step 1: Clone and Configure

**1a. Clone the repository**

```bash
git clone https://github.com/sheria-platform/judicial-mvp.git
cd sheria_platform_mvp
```

**1b. Create your environment file**

```bash
cp .env.example .env
```

**1c. Generate a JWT secret key**

```bash
openssl rand -base64 64
```

Expected output (yours will differ):

```
kP3x+Zq8mN2vR7wL0cE5tY1sA6bD9fH4jM8nQ2pU7vX3zW0yC5eI1oR6tK4lG9hJ2=
```

**1d. Edit `.env` with the required values**

Open `.env` in your editor and set at minimum:

```bash
# Paste the openssl output here
JWT_SECRET_KEY=kP3x+Zq8mN2vR7wL0cE5tY1sA6bD9fH4jM8nQ2pU7vX3zW0yC5eI1oR6tK4lG9hJ2=

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sheria_judicial_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=kenya_law_reports

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=sheriapassword

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.3
OLLAMA_EMBED_MODEL=nomic-embed-text
```

---

## Step 2: Start the Infrastructure

**2a. Start all seven Docker services**

```bash
docker compose up -d
```

**2b. Verify all containers are running**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:

```
NAMES                   STATUS          PORTS
sheria-api              Up 12 seconds   0.0.0.0:8000->8000/tcp
sheria-ollama           Up 12 seconds   0.0.0.0:11434->11434/tcp
sheria-qdrant           Up 13 seconds   0.0.0.0:6333->6333/tcp, 0.0.0.0:6334->6334/tcp
sheria-neo4j            Up 13 seconds   0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
sheria-postgres         Up 13 seconds   0.0.0.0:5432->5432/tcp
sheria-redis            Up 13 seconds   0.0.0.0:6379->6379/tcp
sheria-minio            Up 13 seconds   0.0.0.0:9000->9000/tcp, 0.0.0.0:9001->9001/tcp
```

If any container shows `Exiting` or `Restarting`, check logs with `docker logs <container-name>`.

---

## Step 3: Pull Ollama Models

The LLM and embedding models must be pulled into the running Ollama container. This is a one-time download.

```bash
# Pull the LLM (llama3.3 — approximately 9 GB)
docker exec sheria-ollama ollama pull llama3.3

# Pull the embedding model (nomic-embed-text — approximately 274 MB)
docker exec sheria-ollama ollama pull nomic-embed-text
```

Expected output during pull:

```
pulling manifest
pulling 96c415656d37... 100% |████████████████████| 9.0 GB
pulling 8ab4849b038c... 100% |████████████████████|  274 MB
verifying sha256 digest
writing manifest
success
```

To verify both models are available:

```bash
docker exec sheria-ollama ollama list
```

Expected output:

```
NAME                       ID              SIZE    MODIFIED
llama3.3:latest            a6eb4748fd29    8.8 GB  2 minutes ago
nomic-embed-text:latest    0a109f422b47    274 MB  1 minute ago
```

Alternatively, run the helper script which does both pulls and validates the API endpoints:

```bash
bash scripts/setup_ollama_models.sh
```

---

## Step 4: Verify Services Are Ready

**4a. Liveness check**

```bash
curl -s http://localhost:8000/health/liveness | python3 -m json.tool
```

Expected JSON:

```json
{
    "status": "alive",
    "timestamp": "2026-02-18T09:00:00.000Z"
}
```

**4b. Readiness check (all dependencies)**

```bash
curl -s http://localhost:8000/health/readiness | python3 -m json.tool
```

Expected JSON:

```json
{
    "status": "ready",
    "dependencies": {
        "postgres": "ok",
        "redis": "ok",
        "qdrant": "ok",
        "neo4j": "ok",
        "ollama": "ok",
        "minio": "ok"
    }
}
```

All dependencies must show `"ok"` before proceeding. If any shows `"error"`, check that container's logs.

---

## Step 5: Make Your First API Call

**5a. Obtain a JWT token**

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo_judge", "password": "demo123", "role": "judge"}' \
  | python3 -m json.tool
```

Expected response:

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

**5b. Send a legal research query (streaming)**

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -s -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "What is the legal test for adverse possession under Kenyan land law?",
    "session_id": "demo-session-001",
    "user_role": "judge"
  }'
```

Expected streaming response (NDJSON, one event per line):

```
{"event":"status","data":{"stage":"planner","message":"Refining legal query..."}}
{"event":"status","data":{"stage":"retriever","message":"Searching Kenya Law Reports..."}}
{"event":"status","data":{"stage":"retriever","message":"Querying citation graph..."}}
{"event":"answer","data":{"token":"The"}}
{"event":"answer","data":{"token":" test"}}
{"event":"answer","data":{"token":" for"}}
...
{"event":"done","data":{"citations":["[2019] KECA 45","[2021] KEHC 1203"],"confidence":0.92}}
```

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---|---|---|
| `sheria-ollama` container exits immediately | Insufficient RAM for model weights | Ensure at least 16 GB RAM is free; close other applications |
| `curl: (7) Failed to connect to localhost port 8000` | API container still starting | Wait 30 seconds and retry; check `docker logs sheria-api` |
| Readiness check shows `"qdrant": "error"` | Qdrant collection not yet created | Run `python3 pipelines/ingestion/create_qdrant_collection.py` |
| `401 Unauthorized` on API calls | JWT token missing or expired | Re-fetch token via `/api/v1/auth/login` |
| Ollama `pull` is very slow | Large model download on slow connection | Use `docker exec sheria-ollama ollama pull llama3.2` for a smaller model during development |

For additional diagnostics, inspect logs:

```bash
# API server logs
docker logs sheria-api --tail 50 -f

# Ollama inference logs
docker logs sheria-ollama --tail 50 -f

# All services simultaneously
docker compose logs --tail 20 -f
```

---

## Next Steps

- [docs/API.md](docs/API.md) — Complete API reference with all request/response schemas
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — All environment variables and configuration options
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — Local development guide, code style, and contribution workflow
- [docs/architecture.md](docs/architecture.md) — System architecture deep-dive
