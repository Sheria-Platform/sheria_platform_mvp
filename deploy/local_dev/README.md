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

**model-puller** polls every node via `/api/tags` until models appear before the proxy
starts, eliminating the "service up but model not loaded" race condition.

---

## Prerequisites

| Requirement | CPU profile | GPU profile |
|---|---|---|
| Docker Engine ≥ 24 | required | required |
| Docker Compose plugin | required | required |
| RAM | ≥ 8 GB | ≥ 16 GB |
| nvidia-container-toolkit | not needed | required |
| NVIDIA GPU (VRAM) | not needed | ≥ 8 GB per LLM node |

Install nvidia-container-toolkit on Rocky OS / RHEL:

```bash
# Enable NVIDIA container toolkit repo
curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
  | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
sudo dnf install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
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
curl http://127.0.0.1:8080/health
# → OK

# Confirm models loaded on all backends
curl http://127.0.0.1:8080/probe/llm
curl http://127.0.0.1:8080/probe/embed
curl http://127.0.0.1:8080/probe/rerank

# Open WebUI
open http://localhost:3030
```

### 4. Send a test request

```bash
# LLM — through the proxy (routes round-robin across all 3 LLM nodes)
# CPU profile default model: qwen2.5:3b
# GPU profile default model: qwen3:8b
curl http://localhost:11433/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3:8b",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'

# Embeddings — /api/embed (preferred) or /api/embeddings (alias)
curl http://localhost:11436/api/embed \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "input": "adverse possession test"}'

# Rerank (embed-based similarity scoring)
curl http://localhost:11437/api/embed \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3:8b", "input": "query to score"}'
```

---

## Port Reference

### Proxy ports (use these from your API and services)

| Port | Endpoint | Load balancing |
|------|----------|----------------|
| **11433** | LLM (`/api/chat`, `/api/generate`, `/api/`) | Round-robin: llm + llm2 + llm3 |
| **11436** | Embeddings (`/api/embed`, `/api/embeddings`) | Least-connections: embed node |
| **11437** | Rerank (`/api/embed`, `/api/embeddings`, `/api/chat`) | Least-connections: rerank node |
| **8080**  | Health + status | — |

### Direct node ports (debugging only — bypasses proxy)

| Port | Service | Container |
|------|---------|-----------|
| 11440 | LLM node 1 | `sheria-ollama-llm` |
| 11443 | LLM node 2 | `sheria-ollama-llm2` |
| 11444 | LLM node 3 | `sheria-ollama-llm3` |
| 11441 | Embed node  | `sheria-ollama-embed` |
| 11442 | Rerank node | `sheria-ollama-rerank` |
| 3030  | Open WebUI  | `sheria-open-webui` |

### Health endpoints (port 8080)

| Path | Description |
|------|-------------|
| `/health` | Returns `200 OK` — used by Docker healthcheck and monitoring |
| `/nginx_status` | nginx connection metrics (LAN access only) |
| `/probe/llm` | Proxies to `ollama-llm/api/tags` — confirms LLM node is alive |
| `/probe/embed` | Proxies to `ollama-embed/api/tags` — confirms embed node is alive |
| `/probe/rerank` | Proxies to `ollama-rerank/api/tags` — confirms rerank node is alive |

Probe endpoint format (example with host IP `192.168.50.243`):
```
http://192.168.50.243:8080/probe/embed
http://192.168.50.243:8080/probe/llm
http://192.168.50.243:8080/probe/rerank
```

---

## External Endpoints (LAN Access)

When accessing from another machine or the ingestion pipeline, use the host machine IP.
Replace `192.168.50.243` with your actual machine IP if different.

```env
OLLAMA_LLM_ENDPOINT=http://192.168.50.243:11433/api/chat
OLLAMA_GENERATE_ENDPOINT=http://192.168.50.243:11433/api/generate
OLLAMA_EMBED_ENDPOINT=http://192.168.50.243:11436/api/embed
OLLAMA_RERANK_ENDPOINT=http://192.168.50.243:11437/api/embed
OLLAMA_TAGS_ENDPOINT=http://192.168.50.243:11433/api/tags
```

> **Note:** Port `11434` is internal to the Docker network only. All external access
> must go through the proxy ports above (11433 / 11436 / 11437).

---

## Rocky OS Firewall

Open the required ports with `firewalld` before accessing from other machines:

```bash
# ── User-facing ──────────────────────────────────────────────────
sudo firewall-cmd --permanent --add-port=3030/tcp   # Open WebUI
sudo firewall-cmd --permanent --add-port=8080/tcp   # Nginx health + probes

# ── Ollama Proxy (API clients should use these) ───────────────────
sudo firewall-cmd --permanent --add-port=11433/tcp  # LLM round-robin
sudo firewall-cmd --permanent --add-port=11436/tcp  # Embed
sudo firewall-cmd --permanent --add-port=11437/tcp  # Rerank

# ── Direct node ports (debug / bypass proxy) ──────────────────────
sudo firewall-cmd --permanent --add-port=11440/tcp  # LLM node 1
sudo firewall-cmd --permanent --add-port=11441/tcp  # Embed node
sudo firewall-cmd --permanent --add-port=11442/tcp  # Rerank node
sudo firewall-cmd --permanent --add-port=11443/tcp  # LLM node 2
sudo firewall-cmd --permanent --add-port=11444/tcp  # LLM node 3

sudo firewall-cmd --reload
sudo firewall-cmd --list-ports   # verify
```

To restrict direct node ports to a trusted subnet only:
```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.50.0/24" port port="11440-11444" protocol="tcp" accept'
sudo firewall-cmd --reload
```

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
OLLAMA_RERANK_MODELS=qwen3:8b
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
      ├── Waits for daemon: `ollama list` (same check as the healthcheck)
      ├── Pulls MODELS_TO_PULL (may download from Ollama Hub)
      └── Warms up model: `echo "hi" | timeout 180 ollama run <model>`
          pins model in memory; OLLAMA_KEEP_ALIVE env var keeps it resident

t=0   model-puller starts (parallel with Ollama nodes)
      └── Polls every node's /api/tags via curl until a "name" key appears
          (confirms model is loaded, not just API up)

t=X   model-puller exits 0 → Docker triggers ollama-proxy to start

t=X   ollama-proxy (nginx) starts → healthcheck on http://127.0.0.1:8080/health
      (uses 127.0.0.1 explicitly — localhost resolves to IPv6 inside the container)

t=X   open-webui starts → connects to ollama-proxy:11433
```

If `model-puller` appears stuck: check `docker logs sheria-model-puller` to see
which node it's waiting on, then check that node's logs.

---

## Connecting from the Sheria API / Ingestion Pipeline

Set these in `pipelines/ingestion/.env` (or `services/api/.env`):

**Local (API running on the same host):**
```env
OLLAMA_LLM_ENDPOINT=http://localhost:11433/api/chat
OLLAMA_GENERATE_ENDPOINT=http://localhost:11433/api/generate
OLLAMA_EMBED_ENDPOINT=http://localhost:11436/api/embed
OLLAMA_RERANK_ENDPOINT=http://localhost:11437/api/embed
OLLAMA_TAGS_ENDPOINT=http://localhost:11433/api/tags
```

**Remote / LAN (API on a different machine, cluster on 192.168.50.243):**
```env
OLLAMA_LLM_ENDPOINT=http://192.168.50.243:11433/api/chat
OLLAMA_GENERATE_ENDPOINT=http://192.168.50.243:11433/api/generate
OLLAMA_EMBED_ENDPOINT=http://192.168.50.243:11436/api/embed
OLLAMA_RERANK_ENDPOINT=http://192.168.50.243:11437/api/embed
OLLAMA_TAGS_ENDPOINT=http://192.168.50.243:11433/api/tags
```

**Inside Docker on the same `ollama-net` network:**
```env
OLLAMA_LLM_ENDPOINT=http://ollama-proxy:11433/api/chat
OLLAMA_GENERATE_ENDPOINT=http://ollama-proxy:11433/api/generate
OLLAMA_EMBED_ENDPOINT=http://ollama-proxy:11436/api/embed
OLLAMA_RERANK_ENDPOINT=http://ollama-proxy:11437/api/embed
OLLAMA_TAGS_ENDPOINT=http://ollama-proxy:11433/api/tags
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

# Or use the proxy probes (compact output)
curl -s http://localhost:8080/probe/llm
curl -s http://localhost:8080/probe/embed
curl -s http://localhost:8080/probe/rerank

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
docker logs sheria-ollama-llm
```

Common causes:
- Model download is slow — wait, or check internet connectivity inside container
- `MODELS_TO_PULL` is set to a model name that doesn't exist on Ollama Hub
- Node container exited — `docker ps -a | grep sheria-ollama` to check status

### Proxy healthcheck failing

The nginx healthcheck uses `http://127.0.0.1:8080/health` (not `localhost`) because
Alpine Linux resolves `localhost` to `::1` (IPv6) but nginx only listens on IPv4.
If you see the proxy stuck in `unhealthy`, confirm the fix is in place:

```bash
docker inspect sheria-ollama-proxy --format '{{.State.Health.Status}}'
# Should be: healthy

# Manual test inside the container
docker exec sheria-ollama-proxy wget -q -O- http://127.0.0.1:8080/health
# → OK
```

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
│   └── entrypoint.sh          # each Ollama node: serve → ollama list → pull → warm up → wait
└── README.md                  # this file
```

For the bare-metal remote cluster (LAN IPs, systemd), see:
`resources/script_config/nginx.conf`
