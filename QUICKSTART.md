# Sheria Platform — 5-Minute Quick Start Guide

This guide gets the full Sheria Platform stack running on your local machine in under five minutes. By the end you will have the infrastructure services running, Ollama loaded with the required models, and a working API you can query.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Docker Engine | 24.0+ | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose | 2.24+ | Bundled with Docker Desktop |
| Python | 3.11 | For running scripts outside Docker |
| RAM | 16 GB | Sufficient for `qwen3:8b`, the default dev model |
| Disk space | 10 GB free | Model weights + Docker images |
| NVIDIA GPU | Optional | Significantly speeds up LLM inference in Ollama |

> **macOS users**: Docker Desktop on Apple Silicon (M-series) runs Ollama efficiently on CPU — `qwen3:8b` is small enough to be usable without a GPU.

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

The defaults copied from `.env.example` (Postgres user `ragadmin`, db `rag_db`, Neo4j password `password`, etc.) already match what `docker-compose.yml` provisions for each container, so they work together out of the box — don't hand-edit `DATABASE_URL`/`NEO4J_PASSWORD`/etc. unless you're intentionally changing a service's credentials (and if you do, change it in both places: the service's own var, e.g. `POSTGRES_PASSWORD`, *and* the connection string that embeds it, e.g. `DATABASE_URL`, or they'll disagree). The one value you must change is the JWT secret:

```bash
# Paste the openssl output here
JWT_SECRET_KEY=kP3x+Zq8mN2vR7wL0cE5tY1sA6bD9fH4jM8nQ2pU7vX3zW0yC5eI1oR6tK4lG9hJ2=
```

Also consider changing `ADMIN_PASSWORD` (seeded on first boot) before running this anywhere shared.

---

## Step 2: Start the Infrastructure

**2a. Start the Docker services**

This also builds the `sheria-api` and `sheria-ui` images on first run (both use `build:` — the API from `services/api/Dockerfile`, the frontend from `user_interface/Dockerfile` — not prebuilt images), so the first `up` takes longer than later ones:

```bash
docker compose up -d --build
```

By default (`COMPOSE_PROFILES=cpu` in `.env`) this starts: `postgres`, `redis`, `qdrant`, `neo4j`, `minio`, `ollama` (CPU variant, container name `sheria-ollama`), `sheria-api`, `sheria-ui`, `open-webui`, and `mailhog`. `sheria-ui` runs `next dev` with the `user_interface/` source bind-mounted, so edits on the host apply with hot reload — no rebuild needed.

> **Note:** `ollama-proxy` (nginx load-balancer, ports 11435-11437/8081) is defined in `docker-compose.yml` behind an opt-in `proxy` profile and is skipped by default — it references a `./nginx.conf` that doesn't exist in this repo and is only needed for the separate multi-node `deploy/local_dev/` cluster setup, not this single-node stack. Ignore it unless you're deliberately running `docker compose --profile proxy up -d` with your own `nginx.conf` supplied.

**2b. Verify all containers are running**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:

```
NAMES                   STATUS          PORTS
sheria-api              Up 12 seconds   0.0.0.0:8000->8000/tcp
sheria-ui               Up 10 seconds   0.0.0.0:3000->3000/tcp
sheria-ollama           Up 12 seconds   0.0.0.0:11434->11434/tcp
sheria-qdrant           Up 13 seconds   0.0.0.0:6333->6333/tcp, 0.0.0.0:6334->6334/tcp
sheria-neo4j            Up 13 seconds   0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
sheria-postgres         Up 13 seconds   0.0.0.0:5432->5432/tcp
sheria-redis            Up 13 seconds   0.0.0.0:6379->6379/tcp
sheria-minio            Up 13 seconds   0.0.0.0:9000->9000/tcp, 0.0.0.0:9001->9001/tcp
sheria-open-webui       Up 12 seconds   0.0.0.0:3030->8080/tcp
sheria-mailhog          Up 13 seconds   0.0.0.0:1025->1025/tcp, 0.0.0.0:8025->8025/tcp
```

(`sheria-ollama-proxy` will show `Exited`/`Restarting` — see the note above.) If any *other* container shows `Exiting` or `Restarting`, check logs with `docker logs <container-name>`.

---

## Step 3: Pull Ollama Models

The LLM and embedding models must be pulled into the running Ollama container. This is a one-time download.

```bash
# Pull the LLM (qwen3:8b — approximately 5 GB)
docker exec sheria-ollama ollama pull qwen3:8b

# Pull the embedding model (nomic-embed-text — approximately 274 MB)
docker exec sheria-ollama ollama pull nomic-embed-text
```

Expected output during pull:

```
pulling manifest
pulling 96c415656d37... 100% |████████████████████| 5.2 GB
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
qwen3:8b                   a6eb4748fd29    5.2 GB  2 minutes ago
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
    "status": "ok"
}
```

**4b. Readiness check (all dependencies)**

```bash
curl -s http://localhost:8000/health/readiness | python3 -m json.tool
```

Expected JSON (a flat map, each value `"up"` or `"down"`; the endpoint itself returns HTTP 503 if any dependency is down):

```json
{
    "postgres": "up",
    "redis": "up",
    "qdrant": "up",
    "neo4j": "up",
    "ollama": "up",
    "minio": "up"
}
```

All dependencies must show `"up"` before proceeding. If any shows `"down"`, check that container's logs.

---

## Step 5: Make Your First API Call

**5a. Obtain a JWT token**

New accounts require admin approval before they can log in (see `POST /api/v1/auth/register`), so the fastest path for a first call is the admin account seeded on first boot from `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, default `admin` / `Admin1234` — change this before deploying anywhere shared):

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Admin1234"}' \
  | python3 -m json.tool
```

Expected response:

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user": {
        "id": "...",
        "username": "admin",
        "role": "admin",
        "court": "...",
        "full_name": "System Administrator",
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
}
```

**5b. Send a legal research query (streaming)**

The request body takes `message` (not `query`); role comes from the JWT, not the request:

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -s -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "message": "What is the legal test for adverse possession under Kenyan land law?",
    "session_id": "demo-session-001"
  }'
```

Expected streaming response (NDJSON, one event per line) — one `status` event per LangGraph node, then a single `answer` event with the full response (not token-by-token), then `done`:

```
{"event":"status","step":"planner","session_id":"demo-session-001"}
{"event":"status","step":"retriever","session_id":"demo-session-001"}
{"event":"status","step":"responder","session_id":"demo-session-001"}
{"event":"answer","content":"The test for adverse possession under Kenyan law requires...","session_id":"demo-session-001"}
{"event":"done","session_id":"demo-session-001"}
```

**5c. Or just use the browser**

`sheria-ui` (the Next.js frontend) is already running from Step 2 — open http://localhost:3000 and log in with the same admin credentials from Step 5a. No separate `npm install`/`npm run dev` needed; the container has it covered.

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---|---|---|
| `sheria-ollama` container exits immediately | Insufficient RAM for model weights | Ensure at least 16 GB RAM is free; close other applications |
| `curl: (7) Failed to connect to localhost port 8000` | API container still starting | Wait 30 seconds and retry; check `docker logs sheria-api` |
| Readiness check shows `"qdrant": "down"` | Qdrant collection not yet created | Run `python3 pipelines/ingestion/create_qdrant_collection.py` |
| `401 Unauthorized` on API calls | JWT token missing or expired | Re-fetch token via `/api/v1/auth/login` |
| Ollama `pull` is very slow | Large model download on slow connection | Use `docker exec sheria-ollama ollama pull qwen2.5:3b` for a smaller model during development |
| `sheria-ui` fails with "port 3000 already allocated" | Something else on the host is bound to 3000, or `open-webui`'s port didn't get freed | Check `lsof -i :3000`; if it's a stale `open-webui`, run `docker compose up -d open-webui` to pick up its `OPEN_WEBUI_PORT` (3030) mapping, then retry `sheria-ui` |
| Frontend shows "API unavailable" on login | `sheria-api` isn't healthy yet, or `API_URL` is wrong | Check `docker logs sheria-api`; confirm `docker exec sheria-ui printenv API_URL` prints `http://sheria-api:8000` |

For additional diagnostics, inspect logs:

```bash
# API server logs
docker logs sheria-api --tail 50 -f

# Frontend logs (Next.js dev server)
docker logs sheria-ui --tail 50 -f

# Ollama inference logs
docker logs sheria-ollama --tail 50 -f

# All services simultaneously
docker compose logs --tail 20 -f
```

---

## Next Steps

- [docs/review/API_REFERENCE.md](docs/review/API_REFERENCE.md) — Complete API reference with all request/response schemas
- [ENV_CONFIG_GUIDE.md](ENV_CONFIG_GUIDE.md) — All environment variables and configuration options
- [services/CLAUDE.md](services/CLAUDE.md) — API service architecture, local dev commands, and code layout
- [docs/review/ARCHITECTURE.md](docs/review/ARCHITECTURE.md) — System architecture deep-dive
