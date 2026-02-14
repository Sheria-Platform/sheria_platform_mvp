# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Enterprise RAG (Retrieval Augmented Generation) Platform that combines Vector Search (Qdrant) and Graph Search (Neo4j) for hybrid retrieval. The system uses Ray for distributed compute, vLLM for LLM inference, and FastAPI as the orchestration layer.

## Architecture

The system follows a decoupled architecture with three main layers:

1. **API Layer (Brain)**: FastAPI orchestrator in `services/api/` that handles user requests, authentication, semantic caching, and coordinates the RAG pipeline
2. **AI Engines (Muscle)**: Ray Serve cluster running vLLM and embedding models in `models/`
3. **Data Ingestion Pipeline**: Async Ray Data pipeline in `pipelines/ingestion/` triggered by S3 events

Additional services:

- **Gateway Service** (`services/gateway/`) - API gateway for routing and load balancing
- **Sandbox Service** (`services/sandbox/`) - Secure code execution environment with resource limits

## Local Development Infrastructure

The `docker-compose.yml` defines a complete local development environment with 7 services:

### 1. PostgreSQL (Port 5432)
- **Purpose**: Chat history and metadata storage
- **Image**: `postgres:15-alpine`
- **Credentials**: ragadmin/changeme (see .env.example)
- **Database**: `rag_db`

### 2. Redis (Port 6379)
- **Purpose**: Caching frequently accessed data and semantic cache
- **Image**: `redis:7-alpine`
- **Used by**: API service for semantic query caching

### 3. Qdrant (Ports 6333, 6334)
- **Purpose**: Vector database for embeddings (semantic search)
- **Image**: `qdrant/qdrant:v1.7.3`
- **APIs**: REST (6333), gRPC (6334)
- **Collection**: `rag_collection` (configure in .env)

### 4. Neo4j (Ports 7474, 7687)
- **Purpose**: Graph database for entity relationships
- **Image**: `neo4j:5.16.0-community`
- **UIs**: HTTP Browser (7474), Bolt protocol (7687)
- **Credentials**: neo4j/password

### 5. MinIO (Ports 9000, 9001)
- **Purpose**: S3-compatible object storage for local development
- **Image**: `minio/minio`
- **Console**: http://localhost:9001 (management UI)
- **API**: http://localhost:9000
- **Note**: Caching enabled, excludes *.pdf from cache

### 6. Ollama (Port 11433)
- **Purpose**: Local LLM inference server with GPU support
- **Image**: `ollama/ollama`
- **GPU**: Requires NVIDIA GPU with nvidia-container-toolkit
- **Usage**: Pull models with `docker exec -it ollama ollama pull llama3`

### 7. Open WebUI (Port 3000)
- **Purpose**: Web interface for interacting with Ollama models
- **Image**: `ghcr.io/open-webui/open-webui:main`
- **URL**: http://localhost:3000
- **Features**: RAG support, web search (optional), multi-user auth
- **Integration**: Can optionally use project's Postgres, Redis, and Qdrant

## Development Commands

### Local Development Setup

```bash
# Install all dependencies
make install

# Start local databases (Docker Compose)
make up

# Run FastAPI server with hot reload
make dev

# Stop local databases
make down
```

### Running Individual Services

```bash
# API server (alternative to make dev)
uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env

# Run ingestion pipeline (requires Ray cluster)
python pipelines/ingestion/main.py <bucket_name> <prefix>

# Upload Kenya Law data to MinIO and ingest
python testExample/minio_ingestion.py
```

### Testing

```bash
# Run all tests (Note: tests/ directory not yet implemented)
make test

# Run tests with pytest directly
# pytest tests/
```

### Infrastructure & Deployment

```bash
# Apply Terraform infrastructure
make infra

# Deploy to Kubernetes (EKS)
make deploy
```

## Core Workflow: Request Lifecycle

When a user sends a chat message to `/api/v1/chat/stream`:

1. **FastAPI Orchestrator** (`services/api/main.py`) receives request
2. **Auth Layer** (`services/api/app/auth/`) validates JWT token
3. **Semantic Cache** (`services/api/app/cache/semantic.py`) checks for similar past queries (> 0.95 similarity)
   - If cache hit: return cached answer immediately (Fast Path)
   - If cache miss: proceed to RAG pipeline (Path B)
4. **LangGraph Execution**:
   - **Planner Node**: Refines query using Llama-3
   - **Retriever Node**: Parallel Vector Search (Qdrant) + Graph Search (Neo4j) via `asyncio.gather`
   - **Responder Node**: Synthesizes answer using Ray vLLM (Llama-3-70B)
5. **Streaming Response**: FastAPI streams events as each node completes
6. **Background Tasks**: Save Q&A to Aurora, update semantic cache

## Data Ingestion Pipeline

Located in `pipelines/ingestion/main.py`, this Ray Data pipeline:

1. **Load**: Read files from S3/MinIO using `ray.data.read_binary_files()`
2. **Parse**: Extract text from PDF/DOCX/HTML (`loaders/pdf_loader.py`, `loaders/docx_loader.py`, `loaders/html_loader.py`)
3. **Chunk**: Split into 512-token chunks with 50-token overlap (`chunking/splitter_chunking.py`)
4. **Fork A - Vectorization**:
   - Batch embed chunks via Ray Serve endpoint (`embedding/embedding_compute.py`)
   - Index to Qdrant (`indexing/qdrant_indexing.py`)
5. **Fork B - Knowledge Graph**:
   - Extract entities/relationships using LLM (`graph/extractor_graph.py`)
   - Follow strict schema to prevent hallucination (`graph/schema_graph.py`)
   - Index to Neo4j (`indexing/neo4j_indexing.py`)

### Kenya Law Data Pipeline

For testing with Kenya legal documents, use `testExample/minio_ingestion.py`:

```bash
# Upload Kenya law data to MinIO and trigger ingestion
python testExample/minio_ingestion.py
```

This script:
- Loads files from `kenya_law_data/` directory (case law, regulations, statutes)
- Uploads to MinIO buckets (`rag-dev-kenya-law`, `rag-training-kenya-law`)
- Triggers the Ray Data ingestion pipeline
- Supports PDF, DOCX, HTML, and TXT files
- Adds metadata including upload date, source, and file type

## Key Architectural Patterns

### Shared Libraries (`libs/`)

**Utilities** (`libs/utils/`):
- **ids.py** - Generate session IDs, file IDs (content hash), and trace IDs for distributed tracing
- **timing.py** - Measure execution time for performance monitoring

**Retry Logic** (`libs/retry/`):
- **backoff.py** - Exponential backoff retry mechanism using formula: `base * (2 ^ retries) + random_jitter`

**Observability** (`libs/observability/`):
- **metrics.py** - Application metrics collection (latency, throughput, cache hit rate)
- **tracing.py** - Distributed tracing for debugging across services

**Schemas** (`libs/schemas/`):
- **chat.py** - Pydantic models for chat messages and session management

### Client Connections
All database/service clients are initialized in `services/api/main.py` lifespan context:
- Ray LLM client (`clients/ray_llm.py`)
- Ray Embedding client (`clients/ray_embed.py`)
- Qdrant client (`clients/qdrant.py`)
- Neo4j client (`clients/neo4j.py`)
- Redis client (`cache/redis.py`)

### API Routes

- `/api/v1/chat` - Chat streaming endpoint (`routes/chat.py`)
- `/api/v1/upload` - Document upload to S3 (`routes/upload.py`)
- `/api/v1/feedback` - Feedback collection endpoint (`routes/feedback.py`)
- `/health` - Health check endpoint (`routes/health.py`)

### Agent Tools

The LangGraph agent has access to these tools (`services/api/app/tools/`):

- **vector_search.py** - Semantic search across document embeddings in Qdrant
- **graph_search.py** - Query Neo4j knowledge graph for entity relationships
- **web_search.py** - External web search capability
- **calculator.py** - Mathematical computations
- **sandbox.py** - Secure code execution environment

## Environment Configuration

Copy `.env.example` to `.env` and configure:

- **JWT_SECRET_KEY**: Used for JWT token authentication
- **DATABASE_URL**: Aurora Postgres connection string
- **REDIS_URL**: Redis cache URL
- **QDRANT_HOST/PORT/COLLECTION**: Vector DB configuration
- **NEO4J_URI/USER/PASSWORD**: Graph DB configuration
- **RAY_LLM_ENDPOINT**: Ray Serve LLM endpoint
- **RAY_EMBED_ENDPOINT**: Ray Serve embedding endpoint
- **AWS credentials**: For S3 and EKS deployment
- **WEBUI_SECRET_KEY**: Open WebUI authentication (generate with `openssl rand -base64 32`)

## Scaling Configuration

The system uses multi-level scaling:

1. **Node Scaling**: Karpenter provisions EC2 instances (CPU: `provisioner-cpu.yaml`, GPU: `provisioner-gpu.yaml`)
2. **App Scaling**: Ray Autoscaler manages replica count based on `target_num_ongoing_requests_per_replica`
3. **DB Scaling**: Aurora Serverless v2 auto-scales compute capacity (ACUs)

Configuration files:
- Ray cluster: `deploy/ray/ray-cluster.yaml`
- Ray Serve LLM: `deploy/ray/ray-serve-llm.yaml`
- Ingestion config: `pipelines/ingestion/config.yaml`

## Model Configuration

LLM and embedding model configurations are in `models/`:
- `models/llm/llm_llama-70b.yaml` - Primary LLM (70B parameter)
- `models/llm/llm_llama-7b.yaml` - Smaller LLM variant
- `models/llm/llm_qwen-2b.yaml` - Lightweight model
- `models/embeddings/` - Embedding model configurations
- `models/rerankers/` - Re-ranking model configurations

## Scripts

Utility scripts in `scripts/`:
- `bootstrap_cluster.sh` - Initialize Ray cluster
- `bulk_upload_s3.py` - Bulk upload documents to S3/MinIO
- `migrate_db.py` - Run database migrations
- `load_test.py` - Performance load testing
- `warmup_cache.py` - Pre-populate semantic cache
- `cleanup.sh` - Clean up resources

Example/Test scripts:
- `testExample/minio_ingestion.py` - Kenya Law data upload and ingestion to MinIO
- `data_scrapper/data_scrapper.py` - Web scraping utility for legal data

## Kubernetes Deployment

Helm charts and K8s manifests in `deploy/`:
- `deploy/helm/` - Helm charts for API deployment
- `deploy/ray/` - Ray cluster and Ray Serve configurations
- `deploy/ingress/` - Ingress controller (Nginx/Kong) with rate limiting
- `deploy/secrets/` - K8s secrets management

## Testing API Endpoints

Example curl commands:

```bash
# Chat endpoint
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -d '{
    "message": "What are the key points in the document?",
    "session_id": "test-session-1"
  }'

# Health check
curl http://localhost:8000/health
```

## Infrastructure as Code

Terraform configurations in `infra/terraform/` for AWS resources:
- EKS cluster
- Aurora Postgres
- ElastiCache Redis
- S3 buckets
- VPC and networking
- IAM roles and policies

Karpenter provisioner configs in `infra/karpenter/` for autoscaling nodes.

Local infrastructure setup in `infra/local/` for development environment.

## Evaluation & Quality Assurance

The `eval/` directory contains tools for measuring RAG pipeline quality:

- **RAGAS Metrics** (`eval/ragas/run.py`) - Answer relevancy, faithfulness, context precision/recall
- **LLM Judge** (`eval/judges/llm_judge.py`) - LLM-based evaluation of response quality
- Use these to benchmark performance and detect regression

## Additional Resources

- `proposal_docs/` - Government records digitization system proposals and hackathon documentation and MVP design requirements
- `test_data/` - Sample data for testing
- `kenya_law_data/` - Kenya law documents (case law, regulations, statutes) for ingestion
- `data_scrapper/` - Web scraping tools for collecting legal documents

