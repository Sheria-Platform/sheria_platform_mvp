# Sheria Platform — Ollama Dev Cluster

Role-based Ollama cluster for local development and GPU staging.
Provides load-balanced LLM, embedding, and reranking endpoints behind an nginx proxy,
with automatic model pulling on startup and CPU/GPU profile switching.

---

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │         ollama-proxy (nginx)          │
                    │  :11433 LLM   :11436 Embed            │
                    │  :11437 Rerank  :8080 Health          │
                    └──────┬──────────────┬──────────┬──────┘
                           │              │          │
              ┌────────────┘   ┌──────────┘  ┌──────┘
              ▼                ▼             ▼
       ollama-llm        ollama-embed  ollama-rerank
       ollama-llm2       :11434 (int)  :11434 (int)
       ollama-llm3       ext: 11441    ext: 11442
       :11434 (int each)
       ext: 11440 / 11443 / 11444

  + open-webui (port 3030) → ollama-proxy:11433
  + model-puller (one-shot init container — exits after all models loaded)
```

**3 LLM nodes** handle concurrent requests without queuing: the graph extraction
pipeline fires parallel LLM + embed calls, so 3 nodes = 3 in-flight generations.

**nginx proxy** load-balances across them — your API and WebUI talk only to proxy ports.

**model-puller** polls every node until models appear in `/api/tags` before the proxy starts,
eliminating the "service up but model not loaded" race condition.

---

## Prerequisites

| Requirement | CPU profile | GPU profile |
|---|---|---|
| Docker Engine ≥ 24 | required | required |
| Docker Compose plugin | required | required |
| RAM | ≥ 8 GB | ≥ 16 GB |
| nvidia-container-toolkit | not needed | required |
| NVIDIA GPU (VRAM) | not needed | ≥ 8 GB per LLM node |

Install nvidia-container-toolkit on Ubuntu/Debian:

```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

---

## Quickstart

### 1. Configure environment

```bash
cd deploy/local_dev
cp .env.example .env
```

Edit `.env`:
- Set `COMPOSE_PROFILES=cpu` (laptop) or `COMPOSE_PROFILES=gpu` (workstation)
- Set `WEBUI_SECRET_KEY` to a random string: `openssl rand -base64 32`
- Adjust `OLLAMA_LLM_MODELS` if you want a different model (see [Model Configuration](#model-configuration))

### 2. Start the cluster

**CPU (laptop, no GPU):**
```bash
docker compose --profile cpu up -d
```

**GPU (workstation / staging):**
```bash
docker compose --profile gpu up -d
```

> **First startup is slow.** `model-puller` waits for all models to download before
> the proxy starts. `qwen2.5:3b` (~2 GB) takes 1–3 minutes on a fast connection;
> `qwen3:8b` (~5 GB) takes 3–8 minutes. Subsequent starts are near-instant (cached in volumes).

Watch progress:
```bash
docker logs -f sheria-model-puller    # see which nodes are ready
docker logs -f sheria-ollama-llm      # see model pull + warm-up on node 1
```

### 3. Verify the cluster is up

```bash
# Proxy health
curl http://localhost:8080/health
# → OK

# Models loaded on all 3 LLM nodes
curl http://localhost:8080/probe/llm
curl http://localhost:8080/probe/embed
curl http://localhost:8080/probe/rerank

# Open WebUI
open http://localhost:3030
```

### 4. Send a test request

```bash
# Through the proxy (routes round-robin across all 3 LLM nodes)
curl http://localhost:11433/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'

# Embeddings
curl http://localhost:11436/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "prompt": "adverse possession test"}'
```

---

## Port Reference

### Proxy ports (use these from your API and services)

| Port | Endpoint | Load balancing |
|------|----------|----------------|
| **11433** | LLM (`/api/chat`, `/api/generate`) | Round-robin: llm + llm2 + llm3 |
| **11436** | Embeddings (`/api/embeddings`, `/api/embed`) | Least-connections: embed node |
| **11437** | Rerank (`/api/embeddings`, `/api/chat`) | Least-connections: rerank node |
| **8080** | Health + status | — |

### Direct node ports (debugging only — bypasses proxy)

| Port | Service | Container |
|------|---------|-----------|
| 11440 | LLM node 1 | `sheria-ollama-llm` |
| 11443 | LLM node 2 | `sheria-ollama-llm2` |
| 11444 | LLM node 3 | `sheria-ollama-llm3` |
| 11441 | Embed node | `sheria-ollama-embed` |
| 11442 | Rerank node | `sheria-ollama-rerank` |
| 3030  | Open WebUI | `sheria-open-webui` |

### Health endpoints (port 8080)

| Path | Description |
|------|-------------|
| `/health` | Returns `200 OK` — used by Docker healthcheck |
| `/nginx_status` | nginx connection metrics (LAN access only) |
| `/probe/llm` | Proxies to `ollama-llm:11434/api/tags` |
| `/probe/embed` | Proxies to `ollama-embed:11434/api/tags` |
| `/probe/rerank` | Proxies to `ollama-rerank:11434/api/tags` |

---

## Model Configuration

Models are set per role in `.env`. Change them before first start, or after clearing volumes.

```env
# CPU defaults (smaller models, fits in ~4 GB RAM)
OLLAMA_LLM_MODELS=qwen2.5:3b
OLLAMA_EMBED_MODELS=nomic-embed-text
OLLAMA_RERANK_MODELS=qwen2.5:3b

# GPU recommended
OLLAMA_LLM_MODELS=qwen3:8b
OLLAMA_EMBED_MODELS=nomic-embed-text
OLLAMA_RERANK_MODELS=qwen2.5:3b
```

To pull multiple models into a single node (loaded on demand, one active at a time):
```env
OLLAMA_LLM_MODELS=qwen3:8b,llama3.1:8b
```

To change models on a running cluster, restart the affected service:
```bash
docker compose --profile cpu restart ollama-llm-cpu
docker logs -f sheria-ollama-llm   # watch pull progress
```

---

## Startup Sequence

Understanding this helps debug slow or stuck starts:

```
t=0   All Ollama nodes start → entrypoint.sh runs in each container
      ├── ollama serve starts in background
      ├── Waits for /api/tags to respond
      ├── Pulls MODELS_TO_PULL (may download from Ollama Hub)
      └── Warms up model: pins it in memory with keep_alive=-1

t=0   model-puller starts (parallel with Ollama nodes)
      └── Polls every node's /api/tags until a "name" key appears
          (confirms model is loaded, not just API up)

t=X   model-puller exits 0 → Docker triggers ollama-proxy to start

t=X   ollama-proxy (nginx) starts → healthcheck on /health

t=X   open-webui starts → connects to ollama-proxy:11433
```

If `model-puller` appears stuck: check `docker logs sheria-model-puller` to see
which node it's waiting on, then check that node's logs.

---

## Connecting from the Sheria API

The FastAPI service in `services/api/` connects to the proxy, not individual nodes.
Ensure these are set in `services/api/.env` (or the root `.env`):

```env
RAY_LLM_ENDPOINT=http://localhost:11433    # or ollama-proxy:11433 inside Docker
RAY_EMBED_ENDPOINT=http://localhost:11436
```

If running the API inside Docker on the same `ollama-net` network, use service names:
```env
RAY_LLM_ENDPOINT=http://ollama-proxy:11433
RAY_EMBED_ENDPOINT=http://ollama-proxy:11436
```

---

## Common Operations

```bash
# Stop cluster (keeps model volumes)
docker compose --profile cpu down

# Stop and wipe all model data (forces re-download)
docker compose --profile cpu down -v

# View all running containers
docker ps --filter name=sheria-ollama

# Tail logs from all services
docker compose --profile cpu logs -f

# Check which models are loaded on each node
curl -s http://localhost:11440/api/tags | python3 -m json.tool  # node 1
curl -s http://localhost:11443/api/tags | python3 -m json.tool  # node 2
curl -s http://localhost:11444/api/tags | python3 -m json.tool  # node 3

# List all models in a node (compact)
curl -s http://localhost:11440/api/tags | grep -o '"name":"[^"]*"'

# Delete a model from a node
curl -X DELETE http://localhost:11440/api/delete \
  -d '{"name": "qwen2.5:3b"}'
```

---

## Troubleshooting

### Proxy never starts / model-puller stuck

```bash
docker logs sheria-model-puller
```

It prints which nodes it's waiting on. Check that node's logs:
```bash
docker logs sheria-ollama-llm   # GPU
docker logs sheria-ollama-llm   # CPU (same container name, different service)
```

Common causes:
- Model download is slow — wait, or check internet connectivity inside container
- `MODELS_TO_PULL` is set to a model name that doesn't exist on Ollama Hub
- Node container exited — `docker ps -a | grep sheria-ollama` to check status

### GPU profile fails to start

```
Error response from daemon: could not select device driver "" with capabilities: [[gpu]]
```

nvidia-container-toolkit is not installed or Docker daemon wasn't restarted after install.
Use `--profile cpu` on non-GPU machines — the GPU `deploy.resources` block is only
present in GPU-profile services.

### Port already in use

```bash
# Find what's using a port (e.g. 11433)
lsof -i :11433
```

Change the conflicting port in `.env` and restart:
```bash
OLLAMA_PROXY_LLM_PORT=11450   # change in .env
docker compose --profile cpu up -d
```

### Open WebUI can't connect to Ollama

The WebUI connects to `ollama-proxy:11433` (internal Docker DNS). If you see
"Ollama connection error" in WebUI, the proxy healthcheck probably hasn't passed yet.
Wait ~30 seconds after `model-puller` exits and refresh.

---

## File Reference

```
deploy/local_dev/
├── docker-compose.yml         # cluster definition — roles, profiles, depends_on chain
├── nginx.conf                 # proxy config — upstreams, timeouts, health endpoints
├── .env.example               # all configurable variables with defaults
├── scripts/
│   └── entrypoint.sh          # each Ollama node: serve → pull → warm up → wait
└── README.md                  # this file
```

For the bare-metal remote cluster (LAN IPs, systemd), see:
`resources/script_config/nginx.conf`
