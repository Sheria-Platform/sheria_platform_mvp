# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

This directory contains `services/api/` — the FastAPI orchestration layer for the Sheria Platform. The parent `CLAUDE.md` covers the full project; this file focuses on what is specific to the API service.

## Running the API

All commands are run from the **project root** (`sheria_platform_mvp/`), not from `services/`.

```bash
# Start all infrastructure (Postgres, Redis, Qdrant, Neo4j, Ollama, etc.)
docker-compose up -d

# Run with hot reload (development)
uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env

# Or via Makefile shortcut
make dev

# Install dependencies
pip install -r services/api/requirements.txt

# Run tests
pytest tests/
```

`PYTHONPATH` must include the project root so that `import services.*` and `import libs.*` both resolve. Uvicorn handles this automatically when run from the root; for scripts, set `PYTHONPATH=$(pwd)`.

## Required Environment Variables

These four have no defaults and will prevent startup if missing:

| Variable | Example |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/sheria` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `NEO4J_PASSWORD` | `your_neo4j_password` |
| `JWT_SECRET_KEY` | `openssl rand -base64 32` |

Copy `.env.example` → `.env` and fill these in. All settings live in `services/api/app/config.py` (pydantic-settings).

## Architecture

### Application entry point

`services/api/main.py` creates the FastAPI app and manages all client lifecycles via an async `lifespan` context manager. Startup order: Neo4j → Redis → Qdrant → Ollama. Shutdown is reverse.

**Registered routes:**
- `POST /api/v1/chat/stream` — main streaming RAG endpoint
- `POST /api/v1/upload` — document upload
- `POST /api/v1/feedback`
- `GET /health`

### Client singletons (`services/api/app/clients/`)

Each client is a module-level singleton initialized at import time; lifecycle is managed by `main.py` lifespan:

| Singleton | Class | Purpose |
|---|---|---|
| `ollama_client` | `OllamaClient` | Chat completions via Ollama `/api/chat`; connection pool of 50 |
| `embeddings_client` | `OllamaEmbeddingsClient` | Embeddings via Ollama `/api/embed`; batches of 100; per-request httpx clients |
| `qdrant_client` | `VectorDBClient` | ANN search over Qdrant via gRPC (`prefer_grpc=True`) |
| `neo4j_client` | `Neo4jClient` | Cypher queries over async Neo4j driver |

Both `OllamaClient` and `OllamaEmbeddingsClient` use `@exponential_backoff(max_retries=3)` from `libs/retry/backoff.py`.

### LangGraph agent (`services/api/app/agents/`)

The RAG pipeline is a compiled LangGraph `StateGraph` (`agent_app` in `graph.py`):

```
Planner ──"retrieve"──▶ Retriever ──┐
         ──"tool_use"──▶ Tool      ──┼──▶ Responder ──▶ END
         ──"direct_answer"──────────┘
```

- **Planner** (`nodes/planner.py`): Calls Ollama with `temperature=0.0, json_mode=True` to classify intent and rewrite the query. Falls back to `action="retrieve"` on any error.
- **Retriever** (`nodes/retriever.py`): Embeds the refined query, then runs Qdrant vector search and Neo4j fulltext/graph search **in parallel** via `asyncio.gather`. Deduplicates results before storing in `state["documents"]`.
- **Responder** (`nodes/responder.py`): Synthesises the final answer from `state["documents"]` using Ollama at `temperature=0.3`.
- **Tool** (`nodes/tool.py`): Routes to `calculator` or `graph_search` tools based on `state["tool_choice"]`.

State is defined in `agents/state.py` as `AgentState` (TypedDict). `messages` uses `Annotated[list, operator.add]` so nodes append rather than overwrite.

### Chat request lifecycle (`routes/chat.py`)

1. JWT validation (`auth/jwt.py` → `get_current_user`)
2. Semantic cache lookup (`cache/semantic.py`): embeds query → searches `semantic_cache` Qdrant collection at cosine threshold 0.95
3. Load last 6 conversation turns from `chat_history` table (Postgres via SQLAlchemy asyncpg)
4. Stream LangGraph `agent_app.astream()` as NDJSON (`application/x-ndjson`)
   - Each node completion emits a `{"type": "status", "node": "..."}` event
   - Responder output emits a `{"type": "answer", "content": "..."}` event
5. Background tasks: persist turn to Postgres + write to semantic cache

### Qdrant collections

| Collection | Purpose |
|---|---|
| `kenya_law_reports` | Primary case law collection (configured via `QDRANT_COLLECTION`) |
| `semantic_cache` | Hardcoded in `cache/semantic.py`; stores Q&A pairs for semantic deduplication |

### Dependency injection pattern

`routes/chat.py` wraps global singletons in `get_*()` provider functions and injects them via `Depends()`. This allows `app.dependency_overrides[get_llm_client] = MockClient` in tests without patching.

### Query enhancers (`app/enhancers/`)

- `hyde.py`: Hypothetical Document Embeddings — generates a fake document to improve retrieval similarity (not wired into the main graph yet; available to call explicitly).
- `query_rewriter.py`: Alternative query rewriting strategy.

## Key File Reference

| File | Role |
|---|---|
| `services/api/main.py` | App factory + lifespan |
| `services/api/app/config.py` | All settings (pydantic-settings) |
| `services/api/app/agents/graph.py` | LangGraph graph definition |
| `services/api/app/agents/state.py` | `AgentState` TypedDict |
| `services/api/app/routes/chat.py` | Main streaming endpoint |
| `services/api/app/cache/semantic.py` | Semantic cache (uses `semantic_cache` Qdrant collection) |
| `services/api/app/memory/postgres.py` | `chat_history` ORM + `PostgresMemory` |
| `libs/retry/backoff.py` | `@exponential_backoff` decorator used by Ollama clients |

## Recent Architectural Change

Ollama replaced Ray Serve for LLM inference and embeddings. If you see references to `ray_llm`, `ray_embed`, or `RayLLMClient`, they are outdated — the current implementations are `OllamaClient` and `OllamaEmbeddingsClient`. The Ollama service runs on the standard port `11434` in Docker Compose.
