# Sheria Platform — System Architecture

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                               │
│                                                                     │
│   ┌──────────────────────┐         ┌────────────────────────────┐   │
│   │   Next.js Frontend   │         │   External API Consumers   │   │
│   │  (user_interface/)   │         │   (curl / Postman / SDK)   │   │
│   │  Port: 3000          │         │                            │   │
│   └──────────┬───────────┘         └──────────────┬─────────────┘   │
└──────────────┼──────────────────────────────────── ┼ ───────────────┘
               │  HTTP/HTTPS (REST + NDJSON Stream)  │
               ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER (Brain)                           │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                  FastAPI (services/api/)                    │   │
│   │                       Port: 8000                            │   │
│   │                                                             │   │
│   │  ┌─────────────┐  ┌──────────┐  ┌───────────────────────┐  │   │
│   │  │  Auth Routes│  │  Chat    │  │  Upload/History/Fbk   │  │   │
│   │  │  /auth/*    │  │  /stream │  │  /upload /history     │  │   │
│   │  └─────────────┘  └────┬─────┘  └───────────────────────┘  │   │
│   │                        │                                    │   │
│   │             ┌──────────▼──────────┐                         │   │
│   │             │  Semantic Cache     │  ──── HIT ──────────┐   │   │
│   │             │  (Qdrant + Redis)   │                     │   │   │
│   │             └──────────┬──────────┘                     │   │   │
│   │                        │ MISS                           │   │   │
│   │             ┌──────────▼──────────┐                     │   │   │
│   │             │   LangGraph Agent   │                     │   │   │
│   │             │  Planner → Retriever│                     │   │   │
│   │             │  → Responder → END  │                     │   │   │
│   │             └──────────┬──────────┘                     │   │   │
│   │                        │                                │   │   │
│   └────────────────────────┼────────────────────────────────┼───┘   │
└────────────────────────────┼────────────────────────────────┼───────┘
                             │  Multi-client async calls       │ Cache response
         ┌───────────────────┼───────────────┐                │
         │                   │               │                │
         ▼                   ▼               ▼                ▼
┌────────────────┐  ┌───────────────┐  ┌────────────┐  ┌──────────────┐
│  DATA STORES   │  │  AI ENGINES   │  │  STORAGE   │  │   CACHE      │
│                │  │               │  │            │  │              │
│  ┌──────────┐  │  │  ┌─────────┐  │  │  ┌──────┐  │  │  ┌────────┐  │
│  │PostgreSQL│  │  │  │ Ollama  │  │  │  │MinIO │  │  │  │ Redis  │  │
│  │ Port 5432│  │  │  │Port11434│  │  │  │ 9000 │  │  │  │  6379  │  │
│  └──────────┘  │  │  └─────────┘  │  │  └──────┘  │  │  └────────┘  │
│                │  │    llama3.3   │  │            │  │              │
│  ┌──────────┐  │  │  nomic-embed  │  └────────────┘  └──────────────┘
│  │  Qdrant  │  │  └───────────────┘
│  │6333/6334 │  │
│  └──────────┘  │
│                │
│  ┌──────────┐  │
│  │  Neo4j   │  │
│  │7474/7687 │  │
│  └──────────┘  │
└────────────────┘
```

---

## 2. Service Decomposition

### 2.1 API Service (`services/api/`)

The single FastAPI application that handles all user-facing requests.

**Responsibilities:**
- HTTP request routing and response formatting
- JWT authentication and role-based authorization
- Semantic cache check/write
- LangGraph agent orchestration
- Conversation history persistence
- Presigned URL generation for S3 uploads
- Prometheus metrics exposure
- Structured JSON logging with context injection

**Key Design Patterns:**
| Pattern | Where Used | Why |
|---------|-----------|-----|
| Lifespan context manager | `main.py` | Clean client init/teardown |
| Dependency injection | All routes | FastAPI `Depends()` for auth, DB access |
| Async-first | All I/O | Non-blocking DB, LLM, cache, graph calls |
| Background tasks | Chat, verify routes | Non-blocking history save + cache update |
| Context variables | `logging.py` | Zero-overhead trace context propagation |
| State machine | `agents/graph.py` | Deterministic agent routing (chat) |
| Dedicated retrieval graph | `agents/legal_research_graph.py` | Always-retrieves graph for structured legal research |
| Shared streaming helper | `app/streaming.py` | `iter_agent_events()` generator reused by chat and legal-research routes |
| Query enhancement | `app/enhancers/query_rewriter.py` | Pre-retrieval query rewriting for improved recall |

### 2.2 Data Ingestion Pipeline (`pipelines/ingestion/`)

Separate Ray Data pipeline for processing court documents.

**Responsibilities:**
- Parse PDF, DOCX, and HTML court documents
- Chunk text into 512-token segments with 50-token overlap
- Batch embed chunks via Ollama
- Index embeddings into Qdrant (`kenya_law_reports` collection)
- Extract legal entities and relationships (LLM-powered)
- Index entity graph into Neo4j

**Invocation:**
```bash
python pipelines/ingestion/main.py <bucket_name> <prefix>
# e.g.: python pipelines/ingestion/main.py kenya-law-reports supreme-court/
```

### 2.3 Frontend (`user_interface/`)

Next.js application providing the judge/staff interface.

**Key Pages:**
- `/login` — JWT authentication
- `/register` — Staff registration (status: pending)
- `/activate` — Account activation via emailed token
- `/chat` — Main legal research interface (streaming NDJSON)
- `/history` — Past conversation sessions (with ingestion jobs and verification tabs)
- `/upload` — Document upload to MinIO/S3
- `/jobs` — Ingestion job tracking
- `/verify` — Document verification (Sheria Verify) with upload form and report
- `/health` — Service health dashboard
- `/admin/users` — User management (admin only)

---

## 3. Database Architecture

### 3.1 PostgreSQL — Relational Store (Port 5432)

**Purpose:** User accounts, conversation history, feedback, ingestion job tracking.

**Schema overview:**

```
users                    chat_history              feedback
─────────────────────    ──────────────────────    ──────────────────────
id UUID PK               id UUID PK                id UUID PK
username VARCHAR UNIQUE  session_id VARCHAR         session_id VARCHAR
email VARCHAR UNIQUE     user_id UUID FK→users      user_id UUID FK→users
full_name VARCHAR         role VARCHAR              message_id VARCHAR
hashed_password VARCHAR  content TEXT              score SMALLINT (+1/-1)
role VARCHAR             metadata_ JSONB           comment TEXT
court_station VARCHAR    created_at TIMESTAMPTZ    created_at TIMESTAMPTZ
staff_number VARCHAR
status VARCHAR
activation_token VARCHAR         ingestion_jobs
created_at TIMESTAMPTZ           ──────────────────────────
activated_at TIMESTAMPTZ         job_id VARCHAR PK
                                 user_id UUID FK→users
                                 status VARCHAR
                                 filename VARCHAR
                                 s3_key VARCHAR
                                 started_at TIMESTAMPTZ
                                 completed_at TIMESTAMPTZ
                                 duration_s FLOAT
                                 stats JSONB
                                 error TEXT
```

**Connection:** `asyncpg` via `SQLAlchemy create_async_engine`
- `pool_size=10`, `max_overflow=20`
- Tables created on startup via `Base.metadata.create_all()`

### 3.2 Qdrant — Vector Store (Ports 6333/6334)

**Two collections:**

| Collection | Dimensions | Distance | Purpose |
|-----------|-----------|---------|---------|
| `kenya_law_reports` | 768 | Cosine | Kenya Law Reports embeddings for semantic search |
| `semantic_cache` | 768 | Cosine | Cache of past Q&A pairs indexed by query vector |

**Payload schema for `kenya_law_reports`:**
```json
{
  "text": "...chunk content...",
  "source": "supreme_court/case_001.pdf",
  "court": "Supreme Court",
  "date": "2023-03-15",
  "case_number": "[2023] KESC 45"
}
```

**Payload schema for `semantic_cache`:**
```json
{
  "query": "original user query",
  "answer": "cached AI response",
  "created_at": "2026-03-13T10:00:00Z"
}
```

### 3.3 Neo4j — Graph Store (Ports 7474/7687)

**Purpose:** Citation graph and legal principle relationships.

**Node types:**
- `Case` — A judicial decision
- `Judge` — Individual judge
- `LegalPrinciple` — Legal doctrine or test

**Relationship types:**
- `CITES` — Case → Case (citation)
- `OVERRULES` — Case → Case (precedent reversal)
- `DISTINGUISHES` — Case → Case (factual distinction)
- `APPLIES` — Case → LegalPrinciple
- `PRESIDED` — Judge → Case

**Query pattern in retriever:**
```cypher
CALL db.index.fulltext.queryNodes('legalSearch', $query)
YIELD node, score
MATCH (node)-[r]-(neighbor)
RETURN node.text, neighbor.name, type(r), score
ORDER BY score DESC LIMIT 5
```

### 3.4 Redis — Cache Backing Store (Port 6379)

Used as the backing store for semantic cache metadata. The actual vector similarity is handled by Qdrant; Redis is available for future hot-path caching needs.

---

## 4. Client Connection Architecture

All clients are initialized in `main.py`'s lifespan and stored as FastAPI app state:

```python
app.state.postgres    # PostgresMemory (asyncpg + SQLAlchemy)
app.state.redis       # Redis async client
app.state.qdrant      # QdrantClient (gRPC transport)
app.state.neo4j       # Neo4j async driver
app.state.ollama      # OllamaClient (httpx.AsyncClient pool)
app.state.embeddings  # OllamaEmbeddingsClient
```

**Startup sequence:**
```
1. Create PostgreSQL tables (if not exist)
2. Seed default admin (if no admin exists)
3. Open Neo4j driver
4. Connect Redis client
5. Connect Qdrant (health check)
6. Create semantic_cache collection (if not exist)
7. Start Ollama HTTP client pool
```

**Shutdown sequence (reverse):**
```
7. Close Ollama HTTP client pool
6–1. Close remaining clients in reverse order
```

---

## 5. Request Flow Architecture

### 5.1 Chat Request — Full Lifecycle

```
Client
  │
  │ POST /api/v1/chat/stream
  │ { message, session_id }
  │ Authorization: Bearer <JWT>
  │
  ▼
RequestLoggingMiddleware
  │ Generate trace_id (UUID)
  │ Attach to request state
  │ Start request timer
  │
  ▼
JWT Validation (get_current_user)
  │ Decode token (HS256)
  │ Extract user_id, role, permissions
  │
  ▼
bind_context(trace_id, session_id, user_id)
  │ ContextVar injection for structured logs
  │
  ▼
Semantic Cache Check (Qdrant)
  │ Embed query → 768-dim vector
  │ Search semantic_cache collection
  │ Cosine similarity > 0.95 AND created_at < 30 days?
  │
  ├── HIT ──→ StreamingResponse with cached answer
  │           Background: increment CACHE_HITS metric
  │
  └── MISS ──→
              │
              ▼
        Load Conversation History (PostgreSQL)
              │ Last 6 messages for session
              │
              ▼
        Initialize AgentState
              │ { messages, current_query, query_vector }
              │
              ▼
        LangGraph Execution (stream_events)
              │
              ├──→ Planner Node
              │     │ Ollama JSON mode (temperature=0.0)
              │     │ Output: action, refined_query, reasoning
              │     │ Route: "retrieve" | "direct_answer" | "tool_use"
              │     │
              │     ├── "retrieve" ──→ Retriever Node
              │     │                   │ Embed query (or reuse vector)
              │     │                   │ Parallel:
              │     │                   │  ├── Qdrant semantic search (5 docs)
              │     │                   │  └── Neo4j graph search (5 docs)
              │     │                   │ Deduplicate by content
              │     │                   │
              │     │                   └──→ Responder Node
              │     │
              │     ├── "direct_answer" ──→ Responder Node
              │     │
              │     └── "tool_use" ──→ Tool Node ──→ Responder Node
              │
              ├──→ Responder Node
              │     │ Build IRAC prompt (Issue/Rule/Application/Conclusion)
              │     │ Ollama llama3.3 (temperature=0.3, max_tokens=1024)
              │     │ Stream tokens to client
              │     │
              │     └──→ END
              │
              ▼
        StreamingResponse (NDJSON)
              │ {"event": "status", "node": "planner"}
              │ {"event": "status", "node": "retriever"}
              │ {"event": "answer", "content": "..."}
              │
              ▼
        Background Tasks (fire-and-forget)
              │ ├── Save Q&A to chat_history (PostgreSQL)
              │ └── Update semantic cache (Qdrant)
              │
              ▼
RequestLoggingMiddleware
  │ Record total request latency
  │ Emit structured log: method, path, status, duration_ms, trace_id
  │ Increment REQUEST_COUNT, REQUEST_LATENCY Prometheus metrics
```

### 5.2 Document Upload Flow

```
Client
  │
  │ POST /api/v1/upload/generate-presigned-url
  │ { filename, content_type }
  │
  ▼
FastAPI → boto3.generate_presigned_url()
  │ Key: uploads/{user_id}/{uuid}/{filename}
  │ Expiry: 3600 seconds (1 hour)
  │
  ▼
Response: { upload_url, file_id, s3_key }
  │
  ▼
Client: PUT <file binary> to upload_url (direct to MinIO/S3)
  │
  ▼
[After upload completes, client notifies API]
  │
  ▼
Ingestion Pipeline (Ray Data)
  │ ├── Parse document
  │ ├── Chunk (512 tokens, 50-token overlap)
  │ ├── Embed → Qdrant (kenya_law_reports)
  │ └── Extract entities → Neo4j
```

---

## 6. Embedding Architecture

```
Text Input
    │
    ▼
OllamaEmbeddingsClient.embed(text)
    │ POST /api/embed (Ollama HTTP API)
    │ Model: nomic-embed-text
    │ Timeout: 60s
    │
    ▼
Vector: list[float], dim=768
    │
    ├──→ Qdrant (semantic search / cache insert)
    └──→ AgentState.query_vector (reused across nodes, avoiding re-embedding)
```

**Vector reuse optimization:**
When a cache miss occurs, the embedding computed for the cache lookup is stored in `AgentState.query_vector` and reused in the Retriever node — avoiding a second embedding call for the same query.

---

## 7. Observability Architecture

```
Application Code
    │
    ├── logs ──→ structured JSON logger
    │               (trace_id, session_id, user_id injected via ContextVar)
    │
    ├── metrics ──→ Prometheus client
    │               │
    │               └── GET /metrics (Prometheus scrape endpoint)
    │                   ├── sheria_api_requests_total
    │                   ├── sheria_api_request_duration_seconds
    │                   ├── sheria_cache_hits_total
    │                   ├── sheria_agent_node_duration_seconds
    │                   └── sheria_retrieval_docs_count
    │
    └── traces ──→ OpenTelemetry (libs/observability/tracing.py)
                    (configured but collector not wired in dev)
```

---

## 8. Component Dependency Graph

```
services/api/main.py
    │
    ├── app/routes/chat.py
    │       ├── app/cache/semantic.py ──→ clients/qdrant.py
    │       │                          └─ clients/ollama_embeddings.py
    │       ├── app/streaming.py ──────→ iter_agent_events() shared generator
    │       ├── app/agents/graph.py
    │       │       ├── nodes/planner.py ──→ clients/ollama_client.py
    │       │       ├── nodes/retriever.py ─→ clients/qdrant.py
    │       │       │                      └─ clients/neo4j.py
    │       │       └── nodes/responder.py ─→ clients/ollama_client.py
    │       └── app/memory/postgres.py
    │
    ├── app/routes/legal_research.py
    │       ├── app/cache/semantic.py
    │       ├── app/streaming.py ──────→ iter_agent_events() (shared)
    │       ├── app/agents/legal_research_graph.py
    │       │       ├── nodes/retriever.py (jurisdiction_filter-aware)
    │       │       └── nodes/responder.py (emits structured citations)
    │       └── app/memory/postgres.py
    │
    ├── app/routes/verify.py
    │       ├── app/tools/verify_document.py (LLM + Qdrant pipeline)
    │       └── app/memory/postgres.py (VerificationActivity)
    │
    ├── app/routes/auth.py
    │       ├── app/auth/jwt.py
    │       ├── app/memory/postgres.py
    │       └── app/utils/email.py
    │
    ├── app/routes/upload.py ──→ boto3 (S3/MinIO)
    ├── app/routes/history.py ─→ app/memory/postgres.py
    ├── app/routes/feedback.py → app/memory/postgres.py
    └── app/routes/health.py
```

---

## 9. SOLID Principles Assessment

| Principle | Assessment | Notes |
|-----------|-----------|-------|
| **Single Responsibility (SRP)** | Partial | `memory/postgres.py` owns ORM model definitions AND all persistence methods (chat, users, verification, ingestion jobs). Consider extracting repositories per domain in a future refactor. |
| **Open/Closed (OCP)** | Good | Tool node uses a `TOOLS = {"calculator": ..., ...}` registry — new tools are added via dict insertion without modifying existing node logic. |
| **Liskov Substitution (LSP)** | Good | All Ollama clients (`OllamaClient`, `OllamaEmbeddingsClient`) expose consistent async interfaces; swappable without breaking callers. |
| **Interface Segregation (ISP)** | Partial | `PostgresMemory` exposes methods for chat, auth, users, verification, and ingestion jobs. No consumer needs all of these — consider splitting into `ChatMemory`, `UserRepository`, `VerificationRepository` interfaces. |
| **Dependency Inversion (DIP)** | Good | All routes depend on abstractions via `fastapi.Depends()` (`get_current_user`, `get_memory`, `get_semantic_cache`, `get_llm_client`). Concrete implementations injected at startup via app state. |
