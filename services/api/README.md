# Sheria Platform — API Service

FastAPI application that serves as the AI orchestration layer for the Sheria judicial intelligence platform. It exposes a streaming RAG (Retrieval-Augmented Generation) chat endpoint backed by Ollama (LLM + embeddings), Qdrant (vector search), and Neo4j (citation graph).

---

## Folder Structure

```
services/api/
├── main.py                   # App factory, lifespan (client startup/shutdown), route registration
├── requirements.txt
├── Dockerfile
└── app/
    ├── config.py             # All settings loaded from .env via pydantic-settings
    ├── auth/
    │   └── jwt.py            # JWT Bearer token validation (FastAPI dependency)
    ├── agents/
    │   ├── graph.py          # LangGraph workflow definition (compiled agent_app)
    │   ├── state.py          # AgentState TypedDict shared across all nodes
    │   └── nodes/
    │       ├── planner.py    # Intent classification + query rewriting (Ollama, temp=0)
    │       ├── retriever.py  # Parallel Qdrant + Neo4j search
    │       ├── responder.py  # Final answer synthesis (Ollama, temp=0.3)
    │       └── tool.py       # Calculator / graph search tool executor
    ├── cache/
    │   ├── redis.py          # Redis client wrapper
    │   └── semantic.py       # Semantic cache via Qdrant cosine similarity (threshold 0.95)
    ├── clients/
    │   ├── ollama_client.py      # HTTP client for Ollama /api/chat (connection pool, retries)
    │   ├── ollama_embeddings.py  # HTTP client for Ollama /api/embed (batched, retries)
    │   ├── qdrant.py             # Async Qdrant client over gRPC
    │   └── neo4j.py              # Async Neo4j driver wrapper
    ├── enhancers/
    │   ├── hyde.py           # Hypothetical Document Embeddings (improves retrieval)
    │   └── query_rewriter.py # Alternative query rewriting strategy
    ├── memory/
    │   └── postgres.py       # SQLAlchemy async ORM for chat_history table
    ├── routes/
    │   ├── chat.py           # POST /api/v1/chat/stream — main streaming endpoint
    │   ├── upload.py         # POST /api/v1/upload
    │   ├── feedback.py       # POST /api/v1/feedback
    │   └── health.py         # GET /health/liveness, GET /health/readiness
    └── tools/
        ├── calculator.py
        ├── graph_search.py
        ├── vector_search.py
        └── ...
```

---

## Prerequisites

| Service  | Port  | Purpose                        |
|----------|-------|--------------------------------|
| Postgres | 5432  | Conversation history           |
| Redis    | 6379  | Semantic cache                 |
| Qdrant   | 6333  | Vector search (case law)       |
| Neo4j    | 7687  | Citation graph                 |
| Ollama   | 11434 | LLM inference + embeddings     |

All services are provided by Docker Compose at the project root.

---

## Setup

### 1. Start infrastructure

```bash
# From the project root (sheria_platform_mvp/)
docker-compose up -d
```

Verify everything is running:

```bash
docker-compose ps
```

### 2. Pull Ollama models

The API needs two models: one for chat completions and one for embeddings.

```bash
docker exec -it sheria-ollama ollama pull llama3.3
docker exec -it sheria-ollama ollama pull nomic-embed-text
```

Check available models:

```bash
docker exec -it sheria-ollama ollama list
```

### 3. Configure environment

```bash
# From the project root
cp .env.example .env
```

Open `.env` and set these four **required** fields (all others have working defaults):

```bash
DATABASE_URL=postgresql+asyncpg://ragadmin:changeme@localhost:5432/rag_db
REDIS_URL=redis://localhost:6379/0
NEO4J_PASSWORD=password
JWT_SECRET_KEY=<generate with: openssl rand -base64 32>
```

The Ollama connection defaults to `http://localhost:11434` — change `OLLAMA_BASE_URL` if your Ollama runs elsewhere.

### 4. Install Python dependencies

```bash
# From the project root, using a virtualenv
python -m venv venv && source venv/bin/activate
pip install -r services/api/requirements.txt
```

### 5. Create Qdrant collections

The API expects two Qdrant collections to exist before first run:

- `kenya_law_reports` — main case law collection (dimension must match your embedding model)
- `semantic_cache` — for caching Q&A pairs

```bash
# From the project root
python pipelines/ingestion/create_qdrant_collection.py
```

### 6. Run the API

```bash
# From the project root
uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

Or via Makefile:

```bash
make dev
```

On startup you will see:

```
Initializing clients...
Neo4j driver initialised. uri=bolt://localhost:7687
Redis connected.
Qdrant connected. collections=2
Ollama LLM client initialized.
All clients initialized successfully!
```

---

## Running with Docker

```bash
# Build the image (from project root — the Dockerfile copies both services/ and libs/)
docker build -f services/api/Dockerfile -t sheria-api .

# Run (pass .env file)
docker run --env-file .env -p 8000:8000 sheria-api
```

In Docker Compose the service connects to other containers by hostname (e.g. `OLLAMA_BASE_URL=http://ollama:11434`). For local dev outside Docker use `localhost`.

---

## API Endpoints

### `POST /api/v1/chat/stream`

Main endpoint. Requires a valid JWT in the `Authorization: Bearer` header.

**Request:**
```json
{
  "message": "What is the test for adverse possession in Kenya?",
  "session_id": "optional-uuid-to-continue-a-conversation"
}
```

**Response:** NDJSON stream (`application/x-ndjson`). Each line is a JSON object:

```jsonc
// Node completion status (one per LangGraph node)
{"type": "status", "node": "planner", "session_id": "...", "info": "Completed step: planner"}
{"type": "status", "node": "retriever", "session_id": "...", "info": "Completed step: retriever"}

// Final answer from the responder node
{"type": "answer", "content": "The test for adverse possession...", "session_id": "..."}

// On error
{"type": "error", "content": "An internal error occurred."}
```

### `GET /health/liveness`

Returns `{"status": "ok"}` while the process is alive. Used by Kubernetes liveness probes.

### `GET /health/readiness`

Checks Redis (ping) and Neo4j (driver initialised). Returns `200` when healthy, `503` when not.

```json
{"redis": "up", "neo4j": "up"}
```

---

## How the RAG Pipeline Works

Every chat request runs through a [LangGraph](https://github.com/langchain-ai/langgraph) state machine defined in `app/agents/graph.py`:

```
Request
  │
  ▼
Semantic Cache check ──hit──▶ Stream cached answer
  │ miss
  ▼
Load last 6 messages from Postgres
  │
  ▼
┌──────────┐
│  Planner │  Classifies intent, rewrites query into standalone search form
└──────────┘
  │ "retrieve"           │ "tool_use"         │ "direct_answer"
  ▼                      ▼                    │
┌──────────┐      ┌──────────┐               │
│ Retriever│      │   Tool   │               │
│ (parallel│      │(calc /   │               │
│  Qdrant  │      │ graph    │               │
│  + Neo4j)│      │ search)  │               │
└──────────┘      └──────────┘               │
  │                      │                   │
  └──────────────────────┼───────────────────┘
                         ▼
                  ┌──────────┐
                  │ Responder│  Synthesises answer from retrieved docs
                  └──────────┘
                         │
                         ▼
              Stream answer + save to Postgres
              Write Q&A pair to semantic cache
```

**Shared state** (`AgentState` TypedDict) flows through every node:

| Field | Set by | Used by |
|---|---|---|
| `messages` | chat route, responder | planner, responder |
| `current_query` | planner | retriever, responder |
| `documents` | retriever | responder |
| `action` | planner | graph router |
| `plan` | planner | tool node |
| `tool_choice` / `tool_input` | planner | tool node |

---

## Issuing a JWT for Testing

The API validates tokens against `JWT_SECRET_KEY` using HS256. Generate a test token:

```python
from jose import jwt
import time

token = jwt.encode(
    {"sub": "judge-001", "role": "judge", "exp": time.time() + 3600},
    "your_JWT_SECRET_KEY",
    algorithm="HS256",
)
print(token)
```

Then use it:

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is adverse possession?"}'
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: OllamaClient not initialized` | Ollama not reachable on startup | Check `OLLAMA_BASE_URL` and that Ollama is running |
| `Qdrant connection failed` | Wrong host/port or collection missing | Verify `QDRANT_HOST`/`QDRANT_PORT`; run `create_qdrant_collection.py` |
| `401 Unauthorized` on chat endpoint | JWT missing or wrong secret | Generate token with matching `JWT_SECRET_KEY` |
| Startup fails with `ValidationError` | Missing required env var | Ensure `DATABASE_URL`, `REDIS_URL`, `NEO4J_PASSWORD`, `JWT_SECRET_KEY` are set |
| Empty retrieval results | No data ingested | Run the ingestion pipeline: `python pipelines/ingestion/main.py <bucket> <prefix>` |
