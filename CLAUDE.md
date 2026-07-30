# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sheria Platform** is an AI-powered judicial intelligence ecosystem designed for Kenya's judicial system. It combines Vector Search (Qdrant), Graph Search (Neo4j), and advanced LLM capabilities to provide comprehensive case law research, document verification, court records digitization, and predictive analytics for judges, magistrates, and court staff.

The system uses Ray for distributed compute, vLLM for LLM inference, and FastAPI as the orchestration layer, delivering four integrated modules that transform how judicial data is managed and utilized.

## Target Users

**Primary Users:**
- **Judges & Magistrates**: Legal research, decision support, judgment drafting assistance
- **Court Registrars**: Document verification at filing, case file preparation
- **Judicial Clerks**: Digital file management, exhibit organization, case indexing
- **Chief Justice Office**: System-wide analytics, workload management, resource allocation

**Use Cases:**
- Case law research across Kenya Law Reports (Supreme Court, Court of Appeal, High Court)
- Document authenticity verification (court orders, judgments, evidence)
- Court records digitization with intelligent metadata extraction
- Predictive analytics for case duration, delay risk, and workload optimization
- Judgment drafting with precedent validation and citation formatting
This is an Enterprise RAG (Retrieval Augmented Generation) Platform that combines Vector Search (Qdrant) and Graph Search (Neo4j) for hybrid retrieval. The system uses Ray for distributed compute, vLLM for LLM inference, and FastAPI as the orchestration layer.

## Architecture

The system follows a decoupled architecture with three main layers:

1. **API Layer (Brain)**: FastAPI orchestrator in `services/api/` that handles user requests, authentication, semantic caching, and coordinates the judicial RAG pipeline
2. **AI Engines (Muscle)**: Ray Serve cluster running vLLM and embedding models in `models/`, fine-tuned on Kenya Law Reports and legal documents
3. **Data Ingestion Pipeline**: Async Ray Data pipeline in `pipelines/ingestion/` for processing court records, judgments, and case files

### The Four Judicial Modules

**1. Sheria Digitize (Court Records Intelligence)**
- `pipelines/ingestion/loaders/` - PDF/DOCX parsers for court documents, judgments, pleadings
- `pipelines/ingestion/chunking/` - Legal document chunking (512-token chunks, preserving legal context)
- `pipelines/ingestion/embedding/` - Embedding computation for case law semantic search
- `pipelines/ingestion/graph/` - Extract legal entities (case citations, judges, legal principles)

**2. Sheria Verify (Document Authentication)**
- `services/api/app/tools/verify_document.py` - Court document validation agent
- Integration with: Ministry of Lands (title deeds), LSK (advocate verification), Civil Registration (certificates)
- Fraud detection models for forged court orders and fake judgments

**3. Sheria Ask (Legal Research Assistant)**
- `services/api/app/tools/vector_search.py` - Semantic search across Kenya Law Reports
- `services/api/app/tools/graph_search.py` - Query citation graphs and legal principle relationships
- `services/api/app/agents/legal_research.py` - Conversational AI for case law queries
- Rule-driven legal analysis with cited authorities

**4. Sheria Predict (Judicial Analytics)**
- `services/api/app/tools/predict_case_duration.py` - Case timeline forecasting
- `services/api/app/tools/workload_management.py` - Judge workload optimization
- `services/api/app/agents/judicial_analytics.py` - Predictive insights for case management

Additional services:
- **Gateway Service** (`services/gateway/`) - API gateway for routing and load balancing
- **Sandbox Service** (`services/sandbox/`) - Secure code execution environment (for data analysis)
1. **API Layer (Brain)**: FastAPI orchestrator in `services/api/` that handles user requests, authentication, semantic caching, and coordinates the RAG pipeline
2. **AI Engines (Muscle)**: Ray Serve cluster running vLLM and embedding models in `models/`
3. **Data Ingestion Pipeline**: Async Ray Data pipeline in `pipelines/ingestion/` triggered by S3 events

Additional services:

- **Gateway Service** (`services/gateway/`) - API gateway for routing and load balancing
- **Sandbox Service** (`services/sandbox/`) - Secure code execution environment with resource limits

## Local Development Infrastructure

The `docker-compose.yml` defines a complete local development environment with 7 services:

### 1. PostgreSQL (Port 5432)
- **Purpose**: Case metadata, judicial decisions history, user profiles
- **Judicial Use**: Store case numbers, parties, judges, legal issues, hearing dates
- **Database**: `rag_db` → Consider renaming to `sheria_judicial_db`

### 2. Redis (Port 6379)
- **Purpose**: JWT blacklist for immediate token revocation on logout; used by the `/health` readiness probe
- **Judicial Use**: Invalidate a judge/registrar session immediately on logout, independent of JWT expiry
- **Note**: The semantic cache for legal research queries is backed by Qdrant only (`semantic_cache` collection, 30-day max age), not Redis

### 3. Qdrant (Ports 6333, 6334)
- **Purpose**: Vector database for case law embeddings
- **Judicial Use**: Semantic search across Kenya Law Reports, judgments, statutes
- **Collection**: `rag_collection` → Rename to `kenya_law_reports` for clarity

### 4. Neo4j (Ports 7474, 7687)
- **Purpose**: Citation graph, legal principle relationships
- **Judicial Use**: Map how judgments cite each other, track legal principle evolution
- **Example Query**: "Show all Supreme Court cases citing Muiruri v. Republic"

### 5. MinIO (Ports 9000, 9001)
- **Purpose**: S3-compatible storage for court documents
- **Judicial Use**: Store original PDFs (judgments, pleadings, exhibits)
- **Buckets**: `court-records-dev`, `kenya-law-reports`, `case-files`

### 6. Ollama (Port 11434)
- **Purpose**: Local LLM for development/testing
- **Judicial Use**: Fine-tune on Kenya Law Reports, test legal reasoning locally
- **Models**: Pull legal-specialized models or fine-tune Llama-3 on case law

### 7. Open WebUI (Port 3030)
- **Purpose**: Web interface for testing legal research queries
- **Judicial Use**: Prototype judge interface, test conversational legal research
- **URL**: http://localhost:3030
- **Configuration**: RAG enabled, can integrate with Qdrant for case law search
- **Purpose**: Chat history and metadata storage
- **Image**: `postgres:15-alpine`
- **Credentials**: ragadmin/changeme (see .env.example)
- **Database**: `rag_db`

### 2. Redis (Port 6379)
- **Purpose**: JWT blacklist and readiness health checks (the semantic cache itself is Qdrant-only)
- **Image**: `redis:7-alpine`
- **Used by**: `app/auth/blacklist.py` (token revocation) and `app/routes/health.py` (readiness probe)

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

### 6. Ollama (Port 11434)
- **Purpose**: Local LLM inference server with GPU support
- **Image**: `ollama/ollama`
- **GPU**: Requires NVIDIA GPU with nvidia-container-toolkit
- **Usage**: Pull models with `docker exec -it ollama ollama pull llama3`

### 7. Open WebUI (Port 3030)
- **Purpose**: Web interface for interacting with Ollama models
- **Image**: `ghcr.io/open-webui/open-webui:main`
- **URL**: http://localhost:3030
- **Features**: RAG support, web search (optional), multi-user auth
- **Integration**: Can optionally use project's Postgres, Redis, and Qdrant

## Development Commands

### Local Development Setup

```bash
# Install all dependencies
make install

# Start local databases and AI services (Docker Compose)
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

# Run ingestion pipeline for court records (requires Ray cluster)
python pipelines/ingestion/main.py <bucket_name> <prefix>

# Example: Ingest Kenya Law Reports
python pipelines/ingestion/main.py kenya-law-reports supreme-court/

# Run ingestion pipeline (requires Ray cluster)
python pipelines/ingestion/main.py <bucket_name> <prefix>

# Upload Kenya Law data to MinIO and ingest
python testExample/minio_ingestion.py
```

### Testing

```bash
# Run all tests (Note: tests/ directory to be implemented)
make test

# Test legal research API
curl -X POST http://localhost:8000/api/v1/legal-research \
  -H "Content-Type: application/json" \
  -d '{"query": "adverse possession test Kenya", "user_role": "judge"}'

# Test document verification
curl -X POST http://localhost:8000/api/v1/verify/court-order \
  -H "Content-Type: multipart/form-data" \
  -F "document=@court_order.pdf"
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

## Core Workflow: Judicial Query Lifecycle

When a judge sends a legal research query to `/api/v1/legal-research`:

1. **FastAPI Orchestrator** (`services/api/main.py`) receives request
2. **Auth Layer** (`services/api/app/auth/`) validates JWT token, confirms user is judge/magistrate
3. **Semantic Cache** (`services/api/app/cache/semantic.py`) checks for similar past legal queries
   - If cache hit: return cached case law results immediately (Fast Path)
   - If cache miss: proceed to judicial RAG pipeline (Path B)
4. **LangGraph Execution** (Judicial Research Agent):
   - **Planner Node**: Refines legal query, identifies relevant legal domains (land law, criminal, family, etc.)
   - **Retriever Node**:
     - **Vector Search** (Qdrant): Semantic search across Kenya Law Reports
     - **Graph Search** (Neo4j): Query citation graph for binding precedents
     - **Statutory Search**: Cross-reference relevant statutes and regulations
   - **Analyzer Node**: Apply legal reasoning rules, validate precedent hierarchy
   - **Responder Node**: Synthesize answer with cited authorities, confidence scoring
5. **Streaming Response**: FastAPI streams case law results as each node completes
6. **Background Tasks**:
   - Save query to judicial research history (for analytics)
   - Update semantic cache
   - Log usage for judiciary reporting

## Data Ingestion Pipeline (Court Records)

Located in `pipelines/ingestion/main.py`, this Ray Data pipeline processes court records:

1. **Load**: Read court documents from MinIO/S3 using `ray.data.read_binary_files()`
2. **Parse**:
   - Extract text from PDF judgments (`loaders/pdf_loader.py`)
   - Handle DOCX pleadings (`loaders/docx_loader.py`)
   - Process HTML from Kenya Law website (`loaders/html_loader.py`)
3. **Chunk**:
   - Split into 512-token chunks preserving legal context
   - Special handling: Keep case citations, legal principles, ratio decidendi intact
   - Overlap: 50 tokens to maintain context across chunks
4. **Fork A - Vectorization**:
   - Batch embed chunks via Ray Serve endpoint (`embedding/embedding_compute.py`)
   - Use legal-domain embeddings (fine-tuned on law text)
   - Index to Qdrant collection `kenya_law_reports` (`indexing/qdrant_indexing.py`)
5. **Fork B - Citation Graph**:
   - Extract legal entities: case names, judges, legal principles (`graph/extractor_graph.py`)
   - Extract citations: "as held in [Case Name] [Citation]"
   - Build citation graph in Neo4j (`indexing/neo4j_indexing.py`)
   - Track: Which cases cite which, legal principle evolution

### Kenya Law Data Pipeline

For ingesting Kenya Law Reports, use `testExample/minio_ingestion.py`:
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
- Loads files from `kenya_law_data/` directory (Supreme Court, Court of Appeal, High Court judgments)
- Uploads to MinIO buckets (`kenya-law-reports-dev`, `kenya-law-reports-prod`)
- Triggers the Ray Data ingestion pipeline
- Supports PDF, DOCX, HTML formats
- Adds metadata: court, date, judges, case number, legal subject
- Loads files from `kenya_law_data/` directory (case law, regulations, statutes)
- Uploads to MinIO buckets (`rag-dev-kenya-law`, `rag-training-kenya-law`)
- Triggers the Ray Data ingestion pipeline
- Supports PDF, DOCX, HTML, and TXT files
- Adds metadata including upload date, source, and file type

## Key Architectural Patterns

### Shared Libraries (`libs/`)

**Utilities** (`libs/utils/`):
- **ids.py** - Generate session IDs, case IDs (content hash), trace IDs for distributed tracing
- **timing.py** - Measure execution time for performance monitoring
- **legal_citation.py** - Parse and validate legal citations (Kenya Law format)

**Retry Logic** (`libs/retry/`):
- **backoff.py** - Exponential backoff retry mechanism for external API calls (LSK verification, Land Registry)

**Observability** (`libs/observability/`):
- **metrics.py** - Track: legal research query latency, cache hit rate, API usage per judge
- **tracing.py** - Distributed tracing for debugging across services

**Schemas** (`libs/schemas/`):
- **legal_research.py** - Pydantic models for legal queries, case law results
- **judicial_user.py** - Judge, magistrate, court staff user profiles
- **case_metadata.py** - Case number, parties, legal issues, dates

### Client Connections
All database/service clients are initialized in `services/api/main.py` lifespan context:
- Ray LLM client (`clients/ray_llm.py`) - Legal-domain fine-tuned Llama-3
- Ray Embedding client (`clients/ray_embed.py`) - Legal text embeddings
- Qdrant client (`clients/qdrant.py`) - Kenya Law Reports vector search
- Neo4j client (`clients/neo4j.py`) - Citation graph queries
- Redis client (`cache/redis.py`) - JWT blacklist and health checks (semantic cache is Qdrant-only)

### API Routes (Judicial-Specific)

- `/api/v1/legal-research` - Case law search endpoint (`routes/legal_research.py`)
- `/api/v1/verify/court-order` - Court document verification (`routes/verify_document.py`)
- `/api/v1/predict/case-duration` - Case timeline prediction (`routes/predict.py`)
- `/api/v1/upload/judgment` - Upload court judgment for indexing (`routes/upload.py`)
- `/api/v1/analytics/workload` - Judicial workload analytics (`routes/analytics.py`)
- `/health` - Health check endpoint (`routes/health.py`)

### Agent Tools (Judicial)

The LangGraph legal research agent has access to these tools (`services/api/app/tools/`):

- **vector_search.py** - Semantic search across Kenya Law Reports in Qdrant
- **graph_search.py** - Query Neo4j citation graph for binding precedents
- **statutory_search.py** - Search Kenyan statutes and regulations
- **verify_document.py** - Authenticate court orders, judgments, evidence
- **predict_case_duration.py** - Forecast case timeline based on historical data
- **jurisprudence_consistency.py** - Check if proposed ruling aligns with precedents
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
- Redis client (`cache/redis.py`) - JWT blacklist and health checks (semantic cache is Qdrant-only)

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

### Core Settings
- **JWT_SECRET_KEY**: Used for JWT token authentication (judges, court staff)
- **DATABASE_URL**: PostgreSQL connection for case metadata
- **REDIS_URL**: Redis connection for JWT blacklist and health checks (the semantic cache runs on Qdrant only)

### Vector & Graph Databases
- **QDRANT_HOST/PORT/COLLECTION**: Kenya Law Reports vector DB
  - Collection: `kenya_law_reports`
  - Distance metric: Cosine similarity
  - Vector dimensions: 768 (legal-domain embeddings)
- **NEO4J_URI/USER/PASSWORD**: Citation graph database
  - Nodes: Cases, Judges, Legal Principles
  - Relationships: CITES, OVERRULES, DISTINGUISHES, APPLIES

### AI Engines
- **RAY_LLM_ENDPOINT**: Ray Serve LLM endpoint (legal-domain fine-tuned model)
- **RAY_EMBED_ENDPOINT**: Ray Serve embedding endpoint (legal text embeddings)
- **LEGAL_MODEL_VERSION**: Specify which fine-tuned model to use

### External Integrations
- **LSK_API_KEY**: Law Society of Kenya API for advocate verification
- **LANDS_REGISTRY_API**: Ministry of Lands API for title deed verification
- **CIVIL_REGISTRATION_API**: Birth/death certificate verification
- **JUDICIARY_CMS_API**: Case Management System integration

### Open WebUI (Local Development)
- **WEBUI_SECRET_KEY**: Generate with `openssl rand -base64 32`
- **ENABLE_RAG**: Set to `true` for case law RAG integration
- **RAG_EMBEDDING_MODEL**: `legal-nomic-embed` (fine-tuned for legal text)
- **WEBUI_NAME**: "Sheria Legal Research"

### AWS (for Production Deployment)
- **AWS_REGION**: us-east-1 (or Kenya-specific region when available)
- **S3_BUCKET_NAME**: `sheria-court-records-prod`
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

1. **Node Scaling**: Karpenter provisions EC2 instances
   - CPU-optimized for ingestion pipeline
   - GPU-optimized for LLM inference (legal reasoning)
2. **App Scaling**: Ray Autoscaler manages replica count based on judicial query load
3. **DB Scaling**: Aurora Serverless v2 auto-scales based on case metadata queries

Configuration files:
- Ray cluster: `deploy/ray/ray-cluster.yaml`
- Ray Serve LLM: `deploy/ray/ray-serve-llm-legal.yaml`
1. **Node Scaling**: Karpenter provisions EC2 instances (CPU: `provisioner-cpu.yaml`, GPU: `provisioner-gpu.yaml`)
2. **App Scaling**: Ray Autoscaler manages replica count based on `target_num_ongoing_requests_per_replica`
3. **DB Scaling**: Aurora Serverless v2 auto-scales compute capacity (ACUs)

Configuration files:
- Ray cluster: `deploy/ray/ray-cluster.yaml`
- Ray Serve LLM: `deploy/ray/ray-serve-llm.yaml`
- Ingestion config: `pipelines/ingestion/config.yaml`

## Model Configuration

LLM and embedding model configurations in `models/`:
- `models/llm/llm_llama-70b-legal.yaml` - Legal-domain fine-tuned Llama-3 (70B parameter)
- `models/embeddings/legal-embeddings.yaml` - Fine-tuned on Kenya Law Reports
- `models/rerankers/legal-reranker.yaml` - Re-rank case law results by relevance and precedent hierarchy
LLM and embedding model configurations are in `models/`:
- `models/llm/llm_llama-70b.yaml` - Primary LLM (70B parameter)
- `models/llm/llm_llama-7b.yaml` - Smaller LLM variant
- `models/llm/llm_qwen-2b.yaml` - Lightweight model
- `models/embeddings/` - Embedding model configurations
- `models/rerankers/` - Re-ranking model configurations

## Scripts

Utility scripts in `scripts/`:
- `bootstrap_cluster.sh` - Initialize Ray cluster
- `bulk_upload_judgments.py` - Bulk upload Kenya Law Reports to MinIO
- `migrate_db.py` - Run database migrations for judicial schema
- `load_test_legal_research.py` - Performance load testing for legal queries
- `warmup_cache.py` - **Removed** (deleted during the Ray→Ollama migration); no FAQ cache-warmup script currently exists in `scripts/`
- `cleanup.sh` - Clean up resources

Example/Test scripts:
- `testExample/minio_ingestion.py` - Kenya Law data upload and ingestion
- `scripts/local_minio_ingestion.py` - Local MinIO setup for development
- `scripts/mock_ray_server.py` - Mock Ray server for testing without GPU
- `bulk_upload_s3.py` - Bulk upload documents to S3/MinIO
- `migrate_db.py` - Run database migrations
- `load_test.py` - Performance load testing
- `warmup_cache.py` - **Removed** (deleted during the Ray→Ollama migration); no FAQ cache-warmup script currently exists in `scripts/`
- `cleanup.sh` - Clean up resources

Example/Test scripts:
- `testExample/minio_ingestion.py` - Kenya Law data upload and ingestion to MinIO
- `data_scrapper/data_scrapper.py` - Web scraping utility for legal data

## Kubernetes Deployment

Helm charts and K8s manifests in `deploy/`:
- `deploy/helm/` - Helm charts for API deployment
- `deploy/ray/` - Ray cluster and Ray Serve configurations (legal-specific)
- `deploy/ingress/` - Ingress controller with Judiciary-approved security policies
- `deploy/secrets/` - K8s secrets management (LSK API keys, etc.)

## Testing API Endpoints (Judicial Examples)

### Legal Research Query
```bash
curl -X POST http://localhost:8000/api/v1/legal-research \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -d '{
    "query": "What is the test for adverse possession in Kenya?",
    "user_role": "judge",
    "jurisdiction": ["Supreme Court", "Court of Appeal"],
    "date_range": {"from": "2010-01-01", "to": "2026-02-12"}
  }'

# Response includes:
# - Relevant case law with citations
# - Binding precedents vs persuasive authorities
# - Statutory provisions
# - Legal test summary
```

### Document Verification
```bash
curl -X POST http://localhost:8000/api/v1/verify/court-order \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -F "document=@disputed_court_order.pdf" \
  -F "case_number=HC MISC. APP. 123 OF 2025"

# Response includes:
# - Authenticity: true/false
# - Confidence score: 0.0-1.0
# - Verification sources: [Judiciary CMS, Court Registry]
# - Details: judge, date issued, order type
```

### Case Duration Prediction
```bash
curl -X POST http://localhost:8000/api/v1/predict/case-duration \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -d '{
    "case_type": "land_dispute",
    "parties_count": 6,
    "complexity": "high",
    "court": "High Court Nairobi"
  }'

# Response includes:
# - Estimated duration: 18-24 months
# - Confidence: 0.85
# - Similar cases analyzed: 500
# - Factors contributing to timeline
```

### Workload Analytics (for Chief Justice Office)
```bash
curl -X GET http://localhost:8000/api/v1/analytics/workload?court=High_Court_Nairobi \
  -H "Authorization: Bearer <CJ_JWT_TOKEN>"

# Response includes:
# - Active cases per judge
# - Average case age
# - Backlog statistics
# - Recommended case redistributions
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
- EKS cluster (Kubernetes for Sheria services)
- Aurora Postgres (case metadata, judicial decisions)
- ElastiCache Redis (JWT blacklist, health checks — not the semantic cache, which is Qdrant-only)
- S3 buckets (`sheria-court-records`, `kenya-law-reports`)
- VPC with Judiciary-approved security groups
- IAM roles with least-privilege access
- EKS cluster
- Aurora Postgres
- ElastiCache Redis
- S3 buckets
- VPC and networking
- IAM roles and policies

Karpenter provisioner configs in `infra/karpenter/` for autoscaling nodes.

Local infrastructure setup in `infra/local/` for development environment.

## Evaluation & Quality Assurance

The `eval/` directory contains tools for measuring judicial RAG pipeline quality:

- **Legal Accuracy Metrics** (`eval/legal/accuracy.py`):
  - Precedent citation accuracy
  - Legal reasoning validation
  - Binding vs persuasive authority classification
- **RAGAS Metrics** (`eval/ragas/run.py`): Answer relevancy, faithfulness, context precision
- **Judge Feedback Loop** (`eval/feedback/judicial_review.py`): Judges rate AI suggestions
- Use these to benchmark performance and detect regression in legal reasoning

## Judicial-Specific Considerations

### Data Privacy & Security
- **Sealed Cases**: Special handling for sensitive cases (juvenile, sexual offenses)
- **Access Control**: Role-based (Chief Justice, Presiding Judge, Judge, Registrar, Clerk)
- **Audit Logging**: Every query and document access logged for JSC oversight
- **On-Premise Option**: Deploy within Judiciary's data center for sensitive data

### Legal Domain Fine-Tuning
- **Training Data**: Kenya Law Reports (Supreme Court, Court of Appeal, High Court 2010-2026)
- **Legal Citation Format**: Kenya-specific (e.g., "[2023] KESC 45")
- **Hierarchy Awareness**: System understands court hierarchy and doctrine of precedent
- **Constitutional Context**: Post-2010 Constitution legal framework

### Judicial Independence
- **AI as Assistant**: System provides suggestions, judge makes final decision
- **Transparency**: Every AI suggestion includes cited authority
- **No Automation of Judgment**: AI assists research/drafting, never automates judicial decisions
- **Judge Override**: Judge can ignore AI suggestions; feedback improves model

## Additional Resources

- `proposal_docs/` - Judicial system proposals, MVP design requirements, unified proposal
- `proposal_docs/Sheria_Judicial_System_Unified_Proposal.md` - Comprehensive judicial implementation plan
- `test_data/` - Sample case law data for testing
- `kenya_law_data/` - Kenya Law Reports (Supreme Court, Court of Appeal, High Court judgments)
- `data_scrapper/` - Web scraping tools for collecting Kenya Law website data

## Judicial Workflow Examples

### Judge Morning Routine
1. Log in to Sheria Platform
2. Check dashboard: Reserved judgments approaching 90-day deadline
3. Query: "Show me my cases at high risk of delay"
4. Review case file (digitized, indexed): 10 minutes vs 1 hour previously
5. Legal research for today's hearing: "adverse possession + continuous possession"
6. Review AI-suggested precedents, validate citations
7. Prepared for court: 1 hour vs 4 hours previously

### Judgment Writing Workflow
1. Finish trial, reserve judgment
2. Open Sheria judgment drafting assistant
3. System auto-populates case background from file
4. Judge outlines legal issues to address
5. For each issue, query relevant case law: "test for vicarious liability medical negligence"
6. System provides binding precedents with confidence scores
7. Judge writes reasoning, system validates citations
8. AI checks: All authorities current? No overruled cases? Consistent with precedent?
9. Judgment completed in 1.5 days vs 3 days without AI

### Document Verification at Filing
1. Litigant submits case with land title deed
2. Court Registrar uses Sheria Verify
3. System queries Ministry of Lands database: 30 seconds
4. Result: Title deed authentic, no encumbrances
5. Case accepted for filing immediately (no adjournment for verification)

## Contact & Support

**For Judiciary Deployment Inquiries:**
- Email: judicial-support@sheriaplatform.go.ke
- Judicial Service Commission Liaison: [Contact Info]
- Technical Support: 24/7 for judges, business hours for staff

**Development Team:**
- GitHub: https://github.com/sheria-platform/judicial-mvp
- Documentation: https://docs.sheriaplatform.go.ke
- API Reference: https://api.sheriaplatform.go.ke/docs
The `eval/` directory contains tools for measuring RAG pipeline quality:

- **RAGAS Metrics** (`eval/ragas/run.py`) - Answer relevancy, faithfulness, context precision/recall
- **LLM Judge** (`eval/judges/llm_judge.py`) - LLM-based evaluation of response quality
- Use these to benchmark performance and detect regression

## Additional Resources

- `proposal_docs/` - Government records digitization system proposals and hackathon documentation and MVP design requirements
- `test_data/` - Sample data for testing
- `kenya_law_data/` - Kenya law documents (case law, regulations, statutes) for ingestion
- `data_scrapper/` - Web scraping tools for collecting legal documents
