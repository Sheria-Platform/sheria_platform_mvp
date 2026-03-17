![Sheria Platform Logo](user_interface/public/sheria-logo.svg)

# Sheria Platform

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic--RAG-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![Ollama](https://img.shields.io/badge/Ollama-llama3.3-black.svg)](https://ollama.ai/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

An AI-powered judicial intelligence platform for Kenya's court system. Sheria Platform provides
conversational case law research, document authentication, court records digitization, and
predictive analytics for judges, magistrates, registrars, and court staff.

---

## Contents

- [About](#about)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Building from Source](#building-from-source)
- [Local Services](#local-services)
- [Frontend](#frontend)
- [API Reference](#api-reference)
- [Data Ingestion Pipeline](#data-ingestion-pipeline)
- [Environment Variables](#environment-variables)
- [Observability](#observability)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Reporting Issues](#reporting-issues)
- [Security](#security)
- [Contributing](#contributing)
- [Documentation](#documentation)
- [License](#license)

---

## About

Sheria Platform combines vector semantic search (Qdrant), citation graph traversal (Neo4j), and
large language model reasoning (Ollama / llama3.3) inside a LangGraph agentic pipeline
orchestrated by FastAPI. A Next.js frontend delivers a streaming chat interface for legal research
alongside document upload, conversation history, ingestion job monitoring, and an admin panel.

### Modules

**Sheria Ask** — Legal research assistant. Conversational semantic search across Kenya Law
Reports (Supreme Court, Court of Appeal, High Court) with citation-aware responses and
binding-precedent hierarchy enforcement.

**Sheria Digitize** — Court records ingestion pipeline. Parses PDF, DOCX, HTML, and TXT
documents; chunks text with legal-context preservation; embeds via `nomic-embed-text`; and
indexes to Qdrant and Neo4j simultaneously.

**Sheria Verify** — Document authentication. Accepts a PDF court document, extracts metadata,
runs a three-step LLM and vector similarity verification, and returns a confidence score with
risk flags.

**Sheria Predict** — Judicial analytics. Case duration forecasting and judge workload
optimization (endpoints wired; ML model integration in progress).

---

## Technology Stack

| Layer               | Technology                                   | Version   |
|---------------------|----------------------------------------------|-----------|
| API Framework       | FastAPI                                      | 0.111     |
| Agent Orchestration | LangGraph                                    | Latest    |
| LLM Inference       | Ollama + llama3.3                            | Latest    |
| Embedding Model     | nomic-embed-text (2560-dim)                  | Latest    |
| Vector DB           | Qdrant                                       | v1.7.3    |
| Graph DB            | Neo4j Community                              | 5.16.0    |
| Relational DB       | PostgreSQL + asyncpg + SQLAlchemy            | 15        |
| Cache               | Redis                                        | 7         |
| Object Storage      | MinIO (S3-compatible)                        | Latest    |
| Frontend            | Next.js + React + TypeScript + Tailwind CSS  | 16 / 19   |
| State Management    | Zustand                                      | Latest    |
| Email (Dev)         | MailHog                                      | v1.0.1    |
| Metrics             | Prometheus (prometheus-client)               | Latest    |
| Tracing             | OpenTelemetry                                | Latest    |
| Container Runtime   | Docker Compose                               | 24+       |

---

## Architecture

### System Overview

```
+---------------------------------------------------------------------+
|                          CLIENT LAYER                               |
|                                                                     |
|   +----------------------+         +----------------------------+   |
|   |   Next.js Frontend   |         |   External API Consumers   |   |
|   |  (user_interface/)   |         |   (curl / Postman / SDK)   |   |
|   |  Port: 3000          |         |                            |   |
|   +----------+-----------+         +--------------+-------------+   |
+--------------|-----------------------------------|------------------+
               |  HTTP/HTTPS (REST + NDJSON Stream)|
               v                                   v
+---------------------------------------------------------------------+
|                         API LAYER                                   |
|                                                                     |
|   +-------------------------------------------------------------+   |
|   |           FastAPI  (services/api/)  Port 8000               |   |
|   |                                                             |   |
|   |  +-----------+  +----------+  +-------------------------+  |   |
|   |  | Auth      |  | Chat     |  | Upload / History / Fbk  |  |   |
|   |  | /auth/*   |  | /stream  |  | /verify / /legal-*      |  |   |
|   |  +-----------+  +-----+----+  +-------------------------+  |   |
|   |                       |                                     |   |
|   |          +------------v-----------+                         |   |
|   |          |  Semantic Cache        |--- HIT -------------+   |   |
|   |          |  (Qdrant + Redis)      |                     |   |   |
|   |          +------------+-----------+                     |   |   |
|   |                       | MISS                            |   |   |
|   |          +------------v-----------+                     |   |   |
|   |          |   LangGraph Agent      |                     |   |   |
|   |          |  Planner -> Retriever  |                     |   |   |
|   |          |  -> Responder -> END   |                     |   |   |
|   |          +------------------------+                     |   |   |
|   +-------------------------------------------------------------+   |
+---------------------------------------------------------------------+
                             |
          +------------------+------------------+
          v                  v                  v
+-----------------+  +--------------+  +------------------+
|  DATA STORES    |  |  AI ENGINE   |  |  STORAGE / CACHE |
|                 |  |              |  |                  |
|  PostgreSQL     |  |  Ollama      |  |  MinIO  (9000)   |
|  (5432)         |  |  (11433)     |  |  Redis  (6379)   |
|  Qdrant         |  |  llama3.3    |  +------------------+
|  (6333/6334)    |  |  nomic-embed |
|  Neo4j          |  +--------------+
|  (7474/7687)    |
+-----------------+
```

### LangGraph Agent Pipeline

```
User Query
    |
    v
bind_context(trace_id, session_id, user_id)
    |
    v
Semantic Cache Check  (Qdrant cosine > 0.95, TTL 30 days)
    |
    +-- HIT  --> StreamingResponse (cached answer)
    |
    +-- MISS -->
                |
                v
          Load Conversation History (PostgreSQL -- last 6 messages)
                |
                v
          Planner Node  (Ollama JSON mode, temperature=0.0)
          |
          +-- "retrieve"      --> Retriever Node
          |                         +-- Qdrant semantic search (5 docs)
          |                         +-- Neo4j graph search    (5 docs)
          |                              --> Responder Node
          +-- "direct_answer" --> Responder Node
          +-- "tool_use"      --> Tool Node --> Responder Node
                                       |
                                       v
                                 Responder Node  (llama3.3, temperature=0.3)
                                 IRAC prompt -> stream NDJSON tokens
                                       |
                                       v
                                 Background Tasks
                                 +-- Save to chat_history (PostgreSQL)
                                 +-- Update semantic cache (Qdrant)
```

### Data Ingestion Pipeline

```
MinIO / S3              pipelines/ingestion/main.py
+-----------+
|  PDFs     |
|  DOCX     |--> Parse --> Chunk (512 tok, 50 overlap) --+--> Embed (Ollama) --> Qdrant
|  HTML     |                                            |    (kenya_law_reports)
|  TXT      |                                            |
+-----------+                                            +--> Extract Entities --> Neo4j
                                                              (Case, Judge, Principle)
```

---

## Getting Started

### Prerequisites

| Requirement            | Version       | Notes                          |
|------------------------|---------------|--------------------------------|
| Docker + Docker Compose| 24+           | Required                       |
| Python                 | 3.11          | For local backend development  |
| Node.js                | 18+           | For local frontend development |
| RAM                    | 16 GB minimum | 32 GB recommended with GPU     |
| NVIDIA GPU             | Optional      | Accelerates Ollama inference   |

### Step 1 — Clone

```bash
git clone https://github.com/sheria-platform/judicial-mvp.git
cd sheria_platform_mvp
```

### Step 2 — Configure environment

```bash
cp .env.example .env

# Generate a secure JWT secret key
openssl rand -base64 64
```

Minimum required values in `.env`:

```env
JWT_SECRET_KEY=<generated-value>
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sheria_judicial_db
REDIS_URL=redis://localhost:6379/0
QDRANT_HOST=localhost
OLLAMA_BASE_URL=http://localhost:11433
```

See [ENV_CONFIG_GUIDE.md](ENV_CONFIG_GUIDE.md) for the full variable reference.

### Step 3 — Start infrastructure

```bash
docker compose up -d

# Confirm all containers are healthy
docker ps
```

### Step 4 — Pull Ollama models

```bash
docker exec sheria-ollama ollama pull llama3.3
docker exec sheria-ollama ollama pull nomic-embed-text

# Alternatively, use the helper script
bash scripts/setup_ollama_models.sh
```

### Step 5 — Start the frontend

```bash
cd user_interface
npm install
npm run dev
# Opens at http://localhost:3000
```

See [QUICKSTART.md](QUICKSTART.md) for a full walkthrough including first-login and
default admin credentials.

---

## Building from Source

### Backend

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install all dependencies
pip install -e ".[dev]"
# or: make install && make install-dev

# Run the API server
uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
# or: make dev
```

### Frontend

```bash
cd user_interface
npm install
npm run build    # production build
npm run start    # run production server
```

### Ingestion pipeline

```bash
# Ingest documents from a MinIO bucket
python pipelines/ingestion/main.py <bucket> <prefix> [max_workers] [--enable-graph]

# Example: ingest Supreme Court judgments with graph extraction
python pipelines/ingestion/main.py kenya-law-reports supreme-court/ 4 --enable-graph
```

### Data scraper (standalone)

The scraper has its own Docker setup and runs independently.

```bash
cd data_scrapper
cp .env.example .env
docker compose up -d
# See data_scrapper/QUICKSTART.md for site configuration
```

---

## Local Services

All services start with `docker compose up -d`.

| Service        | Port(s)       | Purpose                                    |
|----------------|---------------|--------------------------------------------|
| sheria-api     | 8000          | FastAPI orchestrator                       |
| Frontend       | 3000          | Next.js interface (npm run dev)            |
| PostgreSQL     | 5432          | User accounts, chat history, ingestion jobs|
| Redis          | 6379          | Semantic cache backing store               |
| Qdrant         | 6333 / 6334   | Vector search (REST / gRPC)                |
| Neo4j Browser  | 7474          | Graph database UI                          |
| Neo4j Bolt     | 7687          | Graph database driver connection           |
| MinIO API      | 9000          | Object storage API                         |
| MinIO Console  | 9001          | Storage management UI                      |
| Ollama         | 11433         | LLM and embedding inference                |
| Ollama Proxy   | 11435 / 11436 | Nginx load balancer for Ollama cluster     |
| Open WebUI     | 3030          | Ollama web interface (dev/testing)         |
| MailHog SMTP   | 1025          | SMTP server for activation emails          |
| MailHog UI     | 8025          | Email capture web UI                       |

---

## Frontend

The Next.js frontend (`user_interface/`) uses the App Router with route groups for
authentication and dashboard flows.

### Pages

| Route                          | Description                                             |
|--------------------------------|---------------------------------------------------------|
| `/`                            | Landing page                                            |
| `/(auth)/login`                | JWT login form                                          |
| `/(auth)/register`             | Staff self-registration (requires admin approval)       |
| `/(auth)/activate`             | Account activation — staff sets password after approval |
| `/(dashboard)/chat`            | Streaming legal research interface                      |
| `/(dashboard)/upload`          | Document upload to MinIO/S3                             |
| `/(dashboard)/history`         | Past conversation sessions                              |
| `/(dashboard)/health`          | Service dependency health dashboard                     |
| `/(dashboard)/jobs`            | Ingestion job monitor                                   |
| `/(dashboard)/admin/users`     | User management (admin role only)                       |

### Components

- `components/chat/` — ChatContainer, MessageList, StreamingIndicator, FeedbackButtons
- `components/upload/` — DropZone, FileList, UploadProgress, IngestionJobsPanel
- `components/layout/` — AppSidebar, TopBar, RoleBadge
- `components/health/` — HealthDashboard, ServiceCard, StatusBadge
- `components/auth/` — LoginForm, AuthPageShell, FormError, SuccessCard
- `components/ui/` — shadcn/ui primitives (button, input, card, dialog, etc.)

---

## API Reference

### Authentication Flow

Registration follows: **Register -> Admin Approval -> Activation -> Login**

| Method | Path                         | Description                         | Auth  |
|--------|------------------------------|-------------------------------------|:-----:|
| POST   | `/api/v1/auth/register`      | Submit registration request         | No    |
| GET    | `/api/v1/auth/pending`       | List registrations awaiting approval| Admin |
| POST   | `/api/v1/auth/approve/{id}`  | Approve a pending user              | Admin |
| POST   | `/api/v1/auth/activate`      | Activate account and set password   | No    |
| POST   | `/api/v1/auth/login`         | Obtain JWT token (8-hour TTL)       | No    |

### Core Endpoints

| Method | Path                                    | Description                              | Auth |
|--------|-----------------------------------------|------------------------------------------|:----:|
| POST   | `/api/v1/chat/stream`                   | Agentic RAG query — streaming NDJSON     | Yes  |
| POST   | `/api/v1/legal-research`                | Kenya Law research with jurisdiction filter | Yes |
| POST   | `/api/v1/verify`                        | Authenticate a court document (PDF)      | Yes  |
| GET    | `/api/v1/history/sessions`              | List user's chat sessions                | Yes  |
| GET    | `/api/v1/history/sessions/{id}`         | Retrieve all messages in a session       | Yes  |
| POST   | `/api/v1/feedback`                      | Submit rating on an AI response          | Yes  |
| POST   | `/api/v1/upload/generate-presigned-url` | Get MinIO/S3 presigned upload URL        | Yes  |

### Health and Observability

| Method | Path                | Description                                                        | Auth |
|--------|---------------------|--------------------------------------------------------------------|:----:|
| GET    | `/health/liveness`  | Container liveness probe                                           | No   |
| GET    | `/health/readiness` | Concurrent check: PostgreSQL, Redis, Qdrant, Neo4j, Ollama, MinIO | No   |
| GET    | `/metrics`          | Prometheus metrics scrape endpoint                                 | No   |

Full request and response schemas: [docs/review/API_REFERENCE.md](docs/review/API_REFERENCE.md)

---

## Data Ingestion Pipeline

The ingestion pipeline (`pipelines/ingestion/`) processes court documents from MinIO/S3 into
Qdrant (vector search) and Neo4j (citation graph).

### Pipeline Components

| Directory    | Purpose                                                           |
|--------------|-------------------------------------------------------------------|
| `loaders/`   | Parse PDF, DOCX, HTML, TXT — dispatched by file extension        |
| `chunking/`  | Split into 512-token chunks with 50-token overlap; enrich with metadata |
| `embedding/` | Batch embed via Ollama `nomic-embed-text` (batches of 100)       |
| `graph/`     | LLM-powered entity extraction (Case, Judge, LegalPrinciple)      |
| `indexing/`  | Write embeddings to Qdrant; write entity graph to Neo4j          |

### Qdrant Collections

| Collection          | Dimensions | Distance | Purpose                           |
|---------------------|------------|----------|-----------------------------------|
| `kenya_law_reports` | 2560       | Cosine   | Kenya Law Reports semantic search |
| `semantic_cache`    | 2560       | Cosine   | Q&A pair cache (30-day TTL)       |

### Neo4j Graph Schema

Nodes: `Case` · `Judge` · `LegalPrinciple`

Relationships: `CITES` · `OVERRULES` · `DISTINGUISHES` · `APPLIES` · `PRESIDED`

### Ingestion Job Tracking

Upload and pipeline status is persisted to the `ingestion_jobs` PostgreSQL table:

```
ingestion_jobs
-----------------------
job_id        VARCHAR PK
user_id       UUID FK -> users
status        VARCHAR
filename      VARCHAR
s3_key        VARCHAR
started_at    TIMESTAMPTZ
completed_at  TIMESTAMPTZ
duration_s    FLOAT
stats         JSONB
error         TEXT
```

---

## Environment Variables

| Variable             | Default                    | Description                               |
|----------------------|----------------------------|-------------------------------------------|
| `JWT_SECRET_KEY`     | —                          | **Required.** HS256 key, minimum 64 chars |
| `JWT_ALGORITHM`      | `HS256`                    | JWT signing algorithm                     |
| `DATABASE_URL`       | —                          | PostgreSQL DSN                            |
| `REDIS_URL`          | `redis://localhost:6379/0` | Redis DSN                                 |
| `QDRANT_HOST`        | `localhost`                | Qdrant host                               |
| `QDRANT_PORT`        | `6333`                     | Qdrant REST port                          |
| `QDRANT_COLLECTION`  | `kenya_law_reports`        | Primary vector collection name            |
| `NEO4J_URI`          | `bolt://localhost:7687`    | Neo4j Bolt URI                            |
| `NEO4J_USER`         | `neo4j`                    | Neo4j username                            |
| `NEO4J_PASSWORD`     | —                          | Neo4j password                            |
| `OLLAMA_BASE_URL`    | `http://localhost:11433`   | Ollama API base URL                       |
| `OLLAMA_LLM_MODEL`   | `llama3.3`                 | LLM model name                            |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text`         | Embedding model name                      |
| `SMTP_HOST`          | `localhost`                | SMTP server (MailHog in dev)              |
| `SMTP_PORT`          | `1025`                     | SMTP port                                 |
| `APP_BASE_URL`       | `http://localhost:8000`    | Used in activation email links            |
| `S3_BUCKET_NAME`     | —                          | S3/MinIO bucket for document uploads      |
| `MINIO_SERVER_URL`   | `http://localhost:9000`    | MinIO endpoint (dev only)                 |
| `LOG_LEVEL`          | `INFO`                     | Application log level                     |
| `ENV`                | `development`              | `development` or `production`             |

---

## Observability

Prometheus metrics exposed at `GET /metrics`:

| Metric                                | Type      | Description                             |
|---------------------------------------|-----------|-----------------------------------------|
| `sheria_api_requests_total`           | Counter   | HTTP requests by method / path / status |
| `sheria_api_request_duration_seconds` | Histogram | HTTP request latency                    |
| `sheria_cache_hits_total`             | Counter   | Semantic cache hits                     |
| `sheria_agent_node_duration_seconds`  | Histogram | Per-node agent execution time           |
| `sheria_retrieval_docs_count`         | Histogram | Retrieved documents per query           |

Structured JSON logs include `trace_id`, `session_id`, and `user_id` automatically injected
via `contextvars` in `services/api/app/logging.py::bind_context()`.

---

## Project Structure

```
sheria_platform_mvp/
|-- services/
|   |-- api/                         # FastAPI orchestrator
|   |   |-- app/
|   |   |   |-- agents/              # LangGraph graphs and nodes
|   |   |   |   |-- graph.py         # Main agentic RAG state machine
|   |   |   |   |-- legal_research_graph.py  # Retriever-only graph for /legal-research
|   |   |   |   |-- nodes/           # planner, retriever, tool, responder
|   |   |   |   |-- state.py         # AgentState TypedDict
|   |   |   |   `-- decorators.py    # @node_timer context manager
|   |   |   |-- auth/                # JWT utilities and RBAC dependency
|   |   |   |-- cache/               # Semantic cache (Qdrant + Redis)
|   |   |   |-- clients/             # Ollama, Qdrant gRPC, Neo4j, async Postgres
|   |   |   |-- memory/              # SQLAlchemy ORM models + PostgresMemory
|   |   |   |-- routes/              # chat, legal_research, auth, upload, verify,
|   |   |   |                        #   feedback, history, health
|   |   |   |-- tools/               # vector_search, graph_search, verify_document,
|   |   |   |                        #   calculator  (web_search + sandbox: stubbed)
|   |   |   |-- utils/               # email (activation), helpers
|   |   |   |-- config.py            # Pydantic Settings
|   |   |   |-- logging.py           # bind_context() + JSONFormatter
|   |   |   |-- streaming.py         # iter_agent_events() NDJSON helper
|   |   |   `-- dependencies.py      # FastAPI Depends() provider functions
|   |   `-- main.py                  # App entry, lifespan, middleware, routes
|   |-- gateway/                     # API gateway (routing, rate limiting)
|   `-- sandbox/                     # Secure code execution (stubbed)
|-- user_interface/                  # Next.js 16 / React 19 frontend
|   |-- app/
|   |   |-- (auth)/                  # login, register, activate
|   |   |-- (dashboard)/             # chat, upload, history, health, jobs, admin/users
|   |   `-- api/auth/                # login and logout Next.js route handlers
|   |-- components/
|   |   |-- chat/                    # ChatContainer, MessageList, FeedbackButtons, etc.
|   |   |-- upload/                  # DropZone, FileList, IngestionJobsPanel, etc.
|   |   |-- layout/                  # AppSidebar, TopBar, RoleBadge
|   |   |-- health/                  # HealthDashboard, ServiceCard, StatusBadge
|   |   |-- auth/                    # LoginForm, AuthPageShell, FormError, SuccessCard
|   |   `-- ui/                      # shadcn/ui primitives
|   `-- public/
|       |-- sheria-logo.svg
|       `-- sheria-logo.jpg
|-- pipelines/
|   `-- ingestion/                   # Court records ingestion pipeline
|       |-- loaders/                 # pdf, docx, html, txt + dispatcher
|       |-- chunking/                # splitter (512 tok) + metadata enrichment
|       |-- embedding/               # Ollama batch embedder
|       |-- graph/                   # LLM entity extractor + schema
|       |-- indexing/                # Qdrant indexer + Neo4j indexer
|       |-- main.py                  # CLI orchestrator
|       `-- server.py                # Web UI for ingestion job management
|-- data_scrapper/                   # Standalone Kenya Law Reports web scraper
|   |-- scraper/
|   |   |-- crawlers/                # KenyaLawCrawler
|   |   |-- parsers/                 # Document metadata extractor
|   |   |-- storage/                 # MinIO upload client
|   |   `-- utils/                   # Rate limiter, validators
|   |-- Dockerfile
|   |-- docker-compose.yml
|   `-- QUICKSTART.md
|-- libs/
|   |-- observability/               # Prometheus metrics + OpenTelemetry tracing
|   |-- retry/                       # Exponential backoff decorator
|   |-- schemas/                     # Shared Pydantic models
|   `-- utils/                       # Session ID, file ID, trace ID generators
|-- tests/
|   |-- conftest.py                  # Pytest fixtures (mock clients)
|   `-- unit/                        # planner, retriever, responder, cache, db pool
|-- docs/
|   |-- review/                      # Architecture, API, Security, BPMN, Data Model
|   `-- proposal_docs/               # Judicial system proposals and whitepapers
|-- deploy/
|   `-- local_dev/                   # Nginx config + local docker-compose override
|-- scripts/
|   |-- bulk_upload_s3.py
|   |-- migrate_db.py
|   `-- setup_ollama_models.sh
|-- resources/                       # Architecture diagrams (21 PNG files)
|-- docker-compose.yml
|-- pyproject.toml                   # ruff + mypy + pytest configuration
|-- .pre-commit-config.yaml
|-- Makefile
`-- .env.example
```

---

## Testing

```bash
# Run all unit tests
make test
# or directly: pytest tests/

# Lint
make lint

# Type check
make type-check

# Format
make format

# Run all pre-commit hooks
pre-commit run --all-files
```

Tests live in `tests/unit/` and cover the planner node, retriever node, responder node,
semantic cache, and PostgreSQL connection pool. All external clients are mocked via fixtures
in `tests/conftest.py`.

---

## Reporting Issues

Report bugs and feature requests via the GitHub issue tracker:

https://github.com/sheria-platform/judicial-mvp/issues

When reporting a bug, include:

- Operating system and version
- Python version (`python --version`)
- Docker version (`docker --version`)
- Steps to reproduce
- Expected vs. actual behaviour
- Relevant log output (`docker logs sheria-api`)

---

## Security

Do **not** report security vulnerabilities in the public issue tracker.

To report a security vulnerability, email **judicial-support@sheriaplatform.go.ke** with
the subject line `[SECURITY] <short description>`. Include a description of the issue,
steps to reproduce, and the potential impact. You will receive a response within 5 business
days.

See [docs/review/SECURITY.md](docs/review/SECURITY.md) for the full security model,
including the authentication flow, role-based access control, and audit logging.

---

## Contributing

Contributions are welcome.

1. Fork the repository and create a feature branch.

    ```bash
    git checkout -b feat/your-feature-name
    ```

2. Follow the code style enforced by the pre-commit hooks (`ruff`, `mypy`, `black`,
   `detect-secrets`).

3. Add or update tests in `tests/`.

4. Run checks locally before opening a pull request.

    ```bash
    pre-commit run --all-files
    pytest tests/
    ```

5. Open a pull request against `main` with a clear description of the change and the
   motivation behind it.

For significant architectural changes, open a GitHub Issue first to align on the approach
before implementing.

---

## Documentation

| Document                                                            | Purpose                                    |
|---------------------------------------------------------------------|--------------------------------------------|
| [QUICKSTART.md](QUICKSTART.md)                                      | 5-minute setup guide                       |
| [ENV_CONFIG_GUIDE.md](ENV_CONFIG_GUIDE.md)                          | Full environment variable reference        |
| [docs/review/ARCHITECTURE.md](docs/review/ARCHITECTURE.md)         | System architecture and data flows         |
| [docs/review/API_REFERENCE.md](docs/review/API_REFERENCE.md)       | API endpoint contracts                     |
| [docs/review/SECURITY.md](docs/review/SECURITY.md)                 | Authentication model and security controls |
| [docs/review/DATA_MODEL.md](docs/review/DATA_MODEL.md)             | Database schemas and ORM models            |
| [docs/review/AGENT_DESIGN.md](docs/review/AGENT_DESIGN.md)         | LangGraph agent internals                  |
| [docs/review/BPMN_WORKFLOWS.md](docs/review/BPMN_WORKFLOWS.md)     | Business process flows                     |
| [docs/review/DEPLOYMENT_GUIDE.md](docs/review/DEPLOYMENT_GUIDE.md) | Docker Compose topology and startup        |
| [data_scrapper/README.md](data_scrapper/README.md)                  | Kenya Law data scraper setup               |
| [pipelines/ingestion/README.md](pipelines/ingestion/README.md)     | Ingestion pipeline reference               |

---

## License

This project is licensed under the Apache License, Version 2.0.
See the [LICENSE](LICENSE) file for the full license text and [NOTICE](NOTICE) for
copyright notices.

---

*Sheria Platform is designed to support — not replace — judicial decision-making.
Every AI suggestion includes a cited authority. The presiding judge retains full
decision-making authority at all times.*
