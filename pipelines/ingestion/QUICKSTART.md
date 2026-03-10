# Ingestion Pipeline — Quick Start Guide

## 5-Minute Setup

### Step 1: Install Ollama

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve
```

### Step 2: Pull Required Models

```bash
# Embedding model (required) — ~275 MB
ollama pull nomic-embed-text

# LLM for graph extraction (required if --enable-graph) — ~4.7 GB
ollama pull llama3

# Verify
ollama list
```

### Step 3: Install Python Dependencies

```bash
cd pipelines/ingestion
pip install -r requirements.txt
```

Key additions in v1.2.0: `jinja2>=3.1.0` (required for the Web Dashboard).

### Step 4: Start Local Infrastructure

```bash
# From project root
make up

# Starts: Qdrant (6333), Neo4j (7474/7687), MinIO (9000/9001), PostgreSQL (5432), Redis (6379)
```

### Step 5: Start the Ingestion Server

```bash
# From repo root
uvicorn pipelines.ingestion.server:app --host 0.0.0.0 --port 8001 --reload
```

Then open <http://localhost:8001/> in your browser — the Web Dashboard loads immediately.

---

## Using the Web Dashboard

The dashboard is served directly from the FastAPI server (no Node.js, no build step).
It uses [htmx 1.9](https://htmx.org/) for server-driven updates,
[Alpine.js 3.14](https://alpinejs.dev/) for drag-and-drop interactions, and
[Pico CSS v2](https://picocss.com/) for styling — all loaded via CDN.

### Upload a File

1. Open <http://localhost:8001/>
2. In the **Upload File** panel, drag a PDF/DOCX/HTML/TXT onto the drop zone, or click to browse
3. Set the target MinIO bucket (default: `api-uploads`)
4. Optionally enable graph extraction
5. Click **Upload & Ingest**

A new job row appears immediately at the top of the Jobs table. The status badge
cycles: `pending` → `running` → `done` / `failed`.

### Trigger Ingestion for an Existing MinIO Prefix

1. In the **Trigger Ingestion** panel, enter your bucket name and prefix
2. Optionally set worker count and batch size
3. Click **Trigger Ingestion**

Use this when files are already in MinIO (e.g. after a bulk upload via the scripts).

### Monitor Jobs

The **Jobs** table auto-refreshes every 3 seconds via htmx polling — no manual refresh needed.

- A blue pulsing dot indicates a running job
- Click a `done` or `failed` row to expand it and see pipeline stats or the error message
- The server health indicator in the header turns red if the server stops responding

---

## CLI Usage (Alternative to the Dashboard)

```bash
# Basic — embeddings only (fast)
python pipelines/ingestion/main.py <bucket_name> <prefix>

# Full — with graph extraction (slow, optional)
python pipelines/ingestion/main.py <bucket_name> <prefix> --enable-graph

# All options
python pipelines/ingestion/main.py <bucket_name> <prefix> \
  --max-workers 8 \
  --file-batch-size 20 \
  --enable-graph \
  --log-level DEBUG

# Kenya Law Reports example
python pipelines/ingestion/main.py kenya-law-reports supreme-court/
```

| Option | Default | Description |
| --- | --- | --- |
| `--max-workers N` | 4 | Parallel download/parse workers |
| `--enable-graph` | off | Enable Neo4j graph extraction |
| `--file-batch-size N` | 10 | Files per worker batch |
| `--log-level` | INFO | DEBUG / INFO / WARNING / ERROR |

---

## JSON API (for programmatic access)

The same server that hosts the dashboard exposes JSON endpoints at `/ingest/*`.
Optionally protect them with `INGEST_API_KEY`.

```bash
# Trigger ingestion
curl -X POST http://localhost:8001/ingest/trigger \
  -H "Content-Type: application/json" \
  -d '{"bucket_name": "my-bucket", "prefix": "docs/", "max_workers": 4}'

# Upload a file
curl -X POST http://localhost:8001/ingest/upload \
  -F "file=@judgment.pdf" \
  -F "bucket_name=api-uploads"

# Poll a job
curl http://localhost:8001/ingest/jobs/<job_id>

# List all jobs
curl http://localhost:8001/ingest/jobs

# Health check
curl http://localhost:8001/health
```

See [README.md](README.md) for full endpoint documentation.

---

## Common Commands

### Infrastructure

```bash
make up       # Start all Docker services
make down     # Stop all Docker services
docker ps     # Check service status
```

### Ollama

```bash
ollama list                          # Installed models
ollama pull mxbai-embed-large        # Higher quality embeddings
ollama pull llama3.1                 # Larger LLM
ollama ps                            # Running models + GPU usage
```

### Verify Ingestion Results

```bash
# Qdrant — vector count
curl http://localhost:6333/collections/kenya_law_reports

# Neo4j — open browser at http://localhost:7474
# Username: neo4j / Password: password
# Cypher: MATCH (n) RETURN labels(n), count(*)
```

---

## Performance Tips

### Use GPU (10x faster)

```bash
ollama ps   # Shows GPU utilisation; Ollama uses GPU automatically if available
```

### Faster embedding model

```bash
ollama pull all-minilm              # 3x faster than nomic-embed-text
export OLLAMA_EMBED_MODEL=all-minilm
```

### More parallelism

```bash
export MAX_WORKERS=8
# or via CLI:
python pipelines/ingestion/main.py <bucket> <prefix> --max-workers 8
```

### Skip graph extraction for initial ingest

```bash
# Graph extraction adds ~30s per document; disable for the first pass
python pipelines/ingestion/main.py <bucket> <prefix>   # no --enable-graph
```

---

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `Connection refused` on Ollama | Run `ollama serve` |
| Dashboard shows "Server unreachable" | Server is down or firewall blocking port 8001 |
| `Unsupported file type` in upload | Only `.pdf`, `.docx`, `.html`, `.htm`, `.txt` accepted |
| Job stuck at `pending` | Check thread pool — max 4 concurrent jobs by default |
| `CUDA out of memory` | Use `ollama pull llama3:8b` or set `OLLAMA_NUM_GPU=0` |
| Slow embeddings | Enable GPU (`ollama ps`) or switch to `all-minilm` |
| Graph extraction returns `{}` | Try `export OLLAMA_LLM_MODEL=qwen2.5` (better JSON output) |
| `jinja2` import error | Run `pip install jinja2>=3.1.0` |

---

## Expected Performance

| Workload | CPU | GPU |
| --- | --- | --- |
| Single 10-page judgment (embeddings only) | ~10s | ~4s |
| Single 10-page judgment (+ graph) | ~40s | ~15s |
| 100 documents with 5 workers | ~20 min | ~8 min |

---

## What Gets Indexed

**Supported formats:** `.pdf` `.docx` `.html` `.htm` `.txt`

### Vector Database (Qdrant)

- Collection: `kenya_law_reports`
- 768-dimensional embeddings (nomic-embed-text)
- Metadata: `case_name`, `citation`, `court`, `date`, `chunk_text`
- Use: semantic search ("Find cases about adverse possession")

### Graph Database (Neo4j)

- Nodes: Cases, Judges, Legal Principles, Statutes
- Relationships: CITES, OVERRULES, DISTINGUISHES, APPLIES
- Use: citation queries ("Show cases citing Muiruri v. Republic")

---

## Setup Checklist

- [ ] Ollama installed and running (`ollama serve`)
- [ ] Models downloaded (`ollama list`)
- [ ] Python dependencies installed — including `jinja2>=3.1.0` (`pip install -r requirements.txt`)
- [ ] Infrastructure running (`docker ps`)
- [ ] Qdrant collection created (`python create_qdrant_collection.py`)
- [ ] Server started (`uvicorn pipelines.ingestion.server:app --port 8001`)
- [ ] Dashboard loads at <http://localhost:8001/>
- [ ] Test upload or trigger succeeds — job appears in Jobs table
- [ ] Data verified in Qdrant (`curl http://localhost:6333/collections/kenya_law_reports`)
- [ ] Graph verified in Neo4j (<http://localhost:7474>)

---

**Ready to ingest!**

For detailed documentation see [README.md](README.md).
