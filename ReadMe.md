# Sheria Platform — Judicial AI Intelligence

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic--RAG-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Ollama](https://img.shields.io/badge/Ollama-llama3.3-black.svg)](https://ollama.ai/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> AI-powered judicial intelligence for Kenya's court system — semantic case law search, document verification, predictive analytics, and judgment drafting assistance.

---

## Overview

Sheria Platform is an end-to-end judicial AI ecosystem purpose-built for the Kenyan judiciary. It combines vector semantic search (Qdrant), citation graph traversal (Neo4j), and large language model reasoning (Ollama / llama3.3) inside a LangGraph agentic pipeline orchestrated by FastAPI. The platform digitizes court records, accelerates legal research, authenticates court documents, and provides data-driven workload analytics — helping judges, magistrates, registrars, and court staff work faster and more accurately.

---

## Features

- **Sheria Ask — Legal Research Assistant**: Conversational semantic search across Kenya Law Reports (Supreme Court, Court of Appeal, High Court) with citation-aware responses and binding-precedent hierarchy enforcement.
- **Sheria Digitize — Court Records Intelligence**: Async ingestion pipeline that parses PDF/DOCX judgments, chunks text with legal-context preservation, embeds via Ollama `nomic-embed-text`, and indexes to Qdrant and Neo4j simultaneously.
- **Sheria Verify — Document Authentication**: AI-powered authenticity verification for court orders, title deeds, and legal certificates via integration with Ministry of Lands, LSK, and Civil Registration APIs.
- **Sheria Predict — Judicial Analytics**: Machine-learning forecasts for case duration, delay risk scoring, and judge workload optimization for the Chief Justice Office.
- **LangGraph Agentic RAG Pipeline**: Modular Planner → Retriever → Analyzer → Responder graph with streaming SSE output, semantic caching (Redis), and per-node observability.
- **Hybrid Search**: Combines dense vector search (Qdrant cosine similarity) with structured citation graph queries (Neo4j) for higher-precision legal research results.
- **Role-Based Access Control**: JWT authentication with roles for Judge, Magistrate, Registrar, Clerk, and Chief Justice, each with scoped tool access and audit logging.
- **Production-Grade Infrastructure**: Docker Compose for local development; AWS EKS with Karpenter autoscaling, Aurora Postgres, and ElastiCache for production deployment.

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              SHERIA PLATFORM                │
                    └─────────────────────────────────────────────┘

  ┌──────────┐        ┌──────────────────────────────────────────────────┐
  │  Client  │──────► │       FastAPI Orchestrator  (Port 8000)          │
  │(Browser/ │  HTTPS │  ┌──────────────┐  ┌──────────┐  ┌───────────┐  │
  │  Mobile) │        │  │  Auth / JWT  │  │ Semantic │  │  Routes   │  │
  └──────────┘        │  │   (RBAC)     │  │  Cache   │  │ Handlers  │  │
                      │  └──────────────┘  │ (Redis)  │  └───────────┘  │
                      │                    └──────────┘                   │
                      └───────────────────────┬──────────────────────────┘
                                              │
                                              ▼
                      ┌──────────────────────────────────────────────────┐
                      │        LangGraph Agentic RAG Pipeline            │
                      │                                                  │
                      │  ┌──────────┐  ┌───────────┐  ┌─────────────┐  │
                      │  │ Planner  │─►│ Retriever │─►│  Analyzer   │  │
                      │  │  Node    │  │   Node    │  │    Node     │  │
                      │  │(refines  │  │(vector +  │  │(legal rules │  │
                      │  │  query)  │  │  graph)   │  │ validation) │  │
                      │  └──────────┘  └─────┬─────┘  └──────┬──────┘  │
                      │                      │                │          │
                      │               ┌──────┴──────┐         │          │
                      │               │   Qdrant    │         ▼          │
                      │               │  (Vectors)  │  ┌────────────┐   │
                      │               └─────────────┘  │ Responder  │   │
                      │               ┌─────────────┐  │ Node (SSE) │   │
                      │               │   Neo4j     │  └────────────┘   │
                      │               │   (Graph)   │                   │
                      │               └─────────────┘                   │
                      └──────────────────────┬───────────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────────┐
                      │              Ollama LLM Engine                   │
                      │  LLM: llama3.3  |  Embeddings: nomic-embed-text  │
                      └──────────────────────────────────────────────────┘
```

### Data Ingestion Pipeline

```
  MinIO / S3               pipelines/ingestion/main.py
  ┌──────────┐
  │  PDFs    │──► Parse ──► Chunk (512 tok) ──┬──► Embed (Ollama) ──► Qdrant
  │  DOCX    │                                │
  │  HTML    │                                └──► Extract Entities ──► Neo4j
  └──────────┘
```

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker + Docker Compose | 24+ | Required |
| Python | 3.11 | For local development |
| RAM | 16 GB minimum | 32 GB recommended with GPU |
| GPU (NVIDIA) | Optional | Accelerates Ollama inference |

### Step 1: Clone the repository

```bash
git clone https://github.com/sheria-platform/judicial-mvp.git
cd sheria_platform_mvp
```

### Step 2: Configure environment

```bash
cp .env.example .env

# Generate a secure JWT secret key and paste into .env
openssl rand -base64 64
```

Edit `.env` and at minimum set:

```
JWT_SECRET_KEY=<generated-value>
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sheria_judicial_db
REDIS_URL=redis://localhost:6379/0
QDRANT_HOST=localhost
OLLAMA_BASE_URL=http://localhost:11434
```

### Step 3: Start all services

```bash
docker compose up -d

# Verify all containers are running
docker ps
```

### Step 4: Pull Ollama models

```bash
docker exec sheria-ollama ollama pull llama3.3
docker exec sheria-ollama ollama pull nomic-embed-text

# Or use the convenience script
bash scripts/setup_ollama_models.sh
```

See [QUICKSTART.md](QUICKSTART.md) for a detailed 5-minute setup guide.

---

## Project Structure

```
sheria_platform_mvp/
├── services/
│   ├── api/                    # FastAPI orchestrator (Brain)
│   │   ├── app/
│   │   │   ├── agents/         # LangGraph agent definitions
│   │   │   ├── auth/           # JWT authentication and RBAC
│   │   │   ├── cache/          # Redis semantic cache
│   │   │   ├── clients/        # Qdrant, Neo4j, Ollama clients
│   │   │   ├── routes/         # HTTP endpoint handlers
│   │   │   └── tools/          # Agent tools (search, verify, predict)
│   │   └── main.py             # FastAPI app entrypoint
│   ├── gateway/                # API gateway and load balancer
│   └── sandbox/                # Secure code execution service
├── pipelines/
│   └── ingestion/              # Court records ingestion pipeline
│       ├── loaders/            # PDF, DOCX, HTML parsers
│       ├── chunking/           # Legal-context-aware text splitting
│       ├── embedding/          # Ollama embedding computation
│       ├── graph/              # Legal entity and citation extraction
│       └── indexing/           # Qdrant and Neo4j indexers
├── libs/
│   ├── utils/                  # IDs, timing, legal citation parsing
│   ├── retry/                  # Exponential backoff for external APIs
│   ├── observability/          # Metrics, distributed tracing
│   └── schemas/                # Pydantic models (legal, judicial user)
├── docs/                       # Documentation
│   ├── API.md
│   ├── CONFIGURATION.md
│   └── DEVELOPMENT.md
├── deploy/
│   ├── helm/                   # Kubernetes Helm charts
│   ├── ray/                    # Ray cluster and Ray Serve configs
│   └── ingress/                # Ingress controller manifests
├── infra/
│   └── terraform/              # AWS EKS, Aurora, ElastiCache IaC
├── eval/                       # RAG evaluation (RAGAS, legal accuracy)
├── scripts/                    # Utility and maintenance scripts
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## API Endpoints

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| `POST` | `/api/v1/chat/stream` | Streaming legal research query (SSE) | Yes |
| `POST` | `/api/v1/feedback/` | Submit feedback on an AI response | Yes |
| `POST` | `/api/v1/upload/generate-presigned-url` | Get MinIO/S3 presigned upload URL | Yes |
| `POST` | `/api/v1/verify/court-order` | Authenticate a court document | Yes |
| `POST` | `/api/v1/predict/case-duration` | Forecast case timeline | Yes |
| `GET` | `/api/v1/analytics/workload` | Judicial workload dashboard data | Yes (CJ role) |
| `GET` | `/health/liveness` | Container liveness probe | No |
| `GET` | `/health/readiness` | Full dependency readiness check | No |

Full request/response schemas: [docs/API.md](docs/API.md)

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | — | **Required.** HS256 signing key (minimum 64 chars) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `DATABASE_URL` | — | PostgreSQL DSN for case metadata |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis DSN for semantic cache |
| `QDRANT_HOST` | `localhost` | Qdrant vector DB host |
| `QDRANT_PORT` | `6333` | Qdrant REST API port |
| `QDRANT_COLLECTION` | `kenya_law_reports` | Qdrant collection name |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | — | Neo4j password |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_LLM_MODEL` | `llama3.3` | LLM model name in Ollama |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model name in Ollama |
| `LOG_LEVEL` | `INFO` | Application log level |
| `ENV` | `development` | Runtime environment (`development` or `production`) |

Full configuration reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## Contributing

Contributions are welcome. Please follow the process below:

1. Fork the repository and create a feature branch: `git checkout -b feat/your-feature-name`
2. Make your changes following the code style guidelines in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
3. Add or update tests in the `tests/` directory.
4. Run `ruff check .` and `black --check .` before committing.
5. Open a Pull Request against the `main` branch with a clear description of the change and the motivation behind it.

For significant architectural changes, open a GitHub Issue first to discuss the approach before implementing.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

*Sheria Platform is designed to support — not replace — judicial decision-making. Every AI suggestion includes a cited authority, and the presiding judge retains full decision-making authority at all times.*
