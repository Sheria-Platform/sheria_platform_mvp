# Configuration Reference — Sheria Platform

This document covers every environment variable and configuration option available in the Sheria Platform. Configuration is loaded at startup from the `.env` file (or from OS environment variables in production Kubernetes deployments).

---

## Table of Contents

1. [Application Settings](#1-application-settings)
2. [Database Settings](#2-database-settings)
3. [Qdrant Vector Database](#3-qdrant-vector-database)
4. [Neo4j Graph Database](#4-neo4j-graph-database)
5. [Ollama LLM Engine](#5-ollama-llm-engine)
6. [Security Settings](#6-security-settings)
7. [MinIO Object Storage](#7-minio-object-storage)
8. [Ingestion Pipeline Settings](#8-ingestion-pipeline-settings)
9. [Docker Compose Overrides](#9-docker-compose-overrides)
10. [Production vs Development Comparison](#10-production-vs-development-comparison)

---

## 1. Application Settings

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `ENV` | `development` | string | Runtime environment. Accepted: `development`, `staging`, `production`. Controls debug output, CORS policy, and error verbosity. |
| `LOG_LEVEL` | `INFO` | string | Python logging level. Accepted: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Use `DEBUG` only in development. |
| `LOG_FORMAT` | `json` | string | Log output format. `json` for structured logging (production); `text` for human-readable (development). |
| `APP_HOST` | `0.0.0.0` | string | Host address the FastAPI server binds to. |
| `APP_PORT` | `8000` | integer | Port the FastAPI server listens on. |
| `WORKERS` | `1` | integer | Number of Uvicorn worker processes. Set to `1` in development; use `(2 * CPU_COUNT) + 1` in production. |
| `RELOAD` | `false` | boolean | Enable Uvicorn hot-reload on file changes. Set to `true` in development only. |
| `CORS_ORIGINS` | `*` | string | Comma-separated list of allowed CORS origins. Restrict to specific domains in production. |
| `API_PREFIX` | `/api/v1` | string | URL prefix for all API routes. |
| `DOCS_ENABLED` | `true` | boolean | Enable FastAPI auto-generated docs at `/docs` and `/redoc`. Disable in production. |
| `REQUEST_TIMEOUT_SECONDS` | `120` | integer | Maximum seconds a single request may run before the server times out the connection. |
| `SEMANTIC_CACHE_TTL` | `86400` | integer | Time-to-live in seconds for cached legal query responses. Default is 24 hours. |

---

## 2. Database Settings

### PostgreSQL

Used for storing case metadata, judicial user profiles, feedback records, and session history.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `DATABASE_URL` | — | string | **Required.** Full PostgreSQL DSN. Format: `postgresql://USER:PASSWORD@HOST:PORT/DBNAME` |
| `DB_POOL_SIZE` | `10` | integer | Number of persistent connections in the SQLAlchemy connection pool. |
| `DB_MAX_OVERFLOW` | `20` | integer | Maximum overflow connections above the pool size. |
| `DB_POOL_TIMEOUT` | `30` | integer | Seconds to wait for a connection before raising a timeout error. |
| `DB_ECHO` | `false` | boolean | Log all SQL statements to stdout. Enable temporarily for query debugging. |

Example value:

```
DATABASE_URL=postgresql://postgres:securepassword@localhost:5432/sheria_judicial_db
```

### Redis

Used as a semantic cache for legal research queries, reducing redundant Ollama inference calls.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | string | Redis connection URL. Format: `redis://[:PASSWORD@]HOST:PORT/DB_NUMBER` |
| `REDIS_MAX_CONNECTIONS` | `50` | integer | Maximum connections in the Redis connection pool. |
| `REDIS_SOCKET_TIMEOUT` | `5` | integer | Seconds before a Redis socket operation times out. |

---

## 3. Qdrant Vector Database

Qdrant stores dense vector embeddings of court documents and case law for semantic similarity search.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `QDRANT_HOST` | `localhost` | string | Qdrant server hostname. |
| `QDRANT_PORT` | `6333` | integer | Qdrant REST API port. |
| `QDRANT_GRPC_PORT` | `6334` | integer | Qdrant gRPC port (used for high-throughput batch upserts in the ingestion pipeline). |
| `QDRANT_COLLECTION` | `kenya_law_reports` | string | Name of the Qdrant collection that stores case law embeddings. |
| `QDRANT_API_KEY` | — | string | Qdrant API key for authenticated Qdrant Cloud deployments. Leave empty for local unauthenticated instances. |
| `QDRANT_VECTOR_SIZE` | `768` | integer | Dimensionality of embedding vectors. Must match the output of `OLLAMA_EMBED_MODEL`. `nomic-embed-text` outputs 768 dimensions. |
| `QDRANT_DISTANCE` | `Cosine` | string | Distance metric. Accepted: `Cosine`, `Euclid`, `Dot`. Cosine is recommended for normalized text embeddings. |
| `QDRANT_TOP_K_DEFAULT` | `5` | integer | Default number of nearest-neighbor results to return from a vector search. |
| `QDRANT_SCORE_THRESHOLD` | `0.70` | float | Minimum cosine similarity score to include a result. Chunks below this threshold are filtered out. |

### Creating the Collection

Before the first ingestion run, create the Qdrant collection:

```bash
python3 pipelines/ingestion/create_qdrant_collection.py
```

---

## 4. Neo4j Graph Database

Neo4j stores the citation graph: court cases as nodes, with directed edges representing CITES, OVERRULES, DISTINGUISHES, and APPLIES relationships.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | string | Neo4j Bolt protocol connection URI. Use `neo4j+s://` for encrypted connections. |
| `NEO4J_USER` | `neo4j` | string | Neo4j database username. |
| `NEO4J_PASSWORD` | — | string | **Required.** Neo4j database password. |
| `NEO4J_DATABASE` | `neo4j` | string | Name of the Neo4j database to connect to. Enterprise Edition supports multiple databases. |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | `50` | integer | Maximum number of Bolt connections maintained in the driver pool. |
| `NEO4J_CONNECTION_TIMEOUT` | `30` | integer | Seconds before a connection attempt to Neo4j times out. |

### Graph Schema

The ingestion pipeline creates the following Neo4j node labels and relationship types:

```
(:Case {citation, title, court, year, url})
  -[:CITES]->(:Case)
  -[:OVERRULES]->(:Case)
  -[:DISTINGUISHES]->(:Case)
  -[:APPLIES]->(:LegalPrinciple {name, description})

(:Judge {name, court, tenure_start, tenure_end})
  -[:PRESIDED_OVER]->(:Case)
```

---

## 5. Ollama LLM Engine

Ollama serves both the chat LLM and the embedding model used throughout the platform.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | string | Base URL of the Ollama HTTP API. Update to `http://sheria-ollama:11434` when both services run in Docker Compose. |
| `OLLAMA_LLM_MODEL` | `llama3.3` | string | Name of the Ollama model used for the LangGraph Responder node. Must be pulled before first use. |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | string | Name of the Ollama model used to generate embeddings in the ingestion pipeline and retriever. Must be pulled before first use. |
| `OLLAMA_REQUEST_TIMEOUT` | `300` | integer | Seconds to wait for an Ollama API response. Increase for very long documents or slow hardware. |
| `OLLAMA_LLM_TEMPERATURE` | `0.1` | float | Sampling temperature for LLM generation. Lower values (0.0-0.2) produce more deterministic legal responses. |
| `OLLAMA_LLM_TOP_P` | `0.9` | float | Nucleus sampling threshold. Works alongside temperature. |
| `OLLAMA_LLM_CTX_SIZE` | `8192` | integer | Context window size in tokens. Larger values allow more retrieved case law context but require more RAM. |
| `OLLAMA_EMBED_BATCH_SIZE` | `32` | integer | Number of text chunks to embed in a single Ollama API call during ingestion. |

### Pulling Models

```bash
# In Docker Compose environment
docker exec sheria-ollama ollama pull llama3.3
docker exec sheria-ollama ollama pull nomic-embed-text

# List available models
docker exec sheria-ollama ollama list

# Check model details
docker exec sheria-ollama ollama show llama3.3
```

### Alternative Models

| Use Case | Model | Notes |
|---|---|---|
| Development (fast, small) | `llama3.2` | ~2 GB, faster inference, lower quality |
| Development (medium) | `mistral` | ~4 GB, good instruction following |
| Production (high quality) | `llama3.3` | ~9 GB, recommended for judicial tasks |
| Embeddings (default) | `nomic-embed-text` | 768-dim, optimized for semantic search |
| Embeddings (alternative) | `mxbai-embed-large` | 1024-dim, higher accuracy |

---

## 6. Security Settings

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | — | string | **Required.** Secret key for signing JWT tokens. Generate with `openssl rand -base64 64`. Minimum 64 characters. Rotate periodically. |
| `JWT_ALGORITHM` | `HS256` | string | JWT signing algorithm. `HS256` for symmetric; `RS256` for asymmetric (production recommended). |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | integer | Number of minutes before a JWT access token expires. |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | integer | Number of days before a refresh token expires. |
| `BCRYPT_ROUNDS` | `12` | integer | bcrypt work factor for password hashing. Higher values are more secure but slower. |
| `ALLOWED_HOSTS` | `*` | string | Comma-separated list of allowed request hostnames. Restrict in production. |
| `HTTPS_ONLY` | `false` | boolean | Reject all non-HTTPS requests. Set to `true` in production. |

---

## 7. MinIO Object Storage

MinIO stores the original court document files (PDFs, DOCX) before ingestion.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9000` | string | MinIO server endpoint (host:port). |
| `MINIO_ACCESS_KEY` | `minioadmin` | string | MinIO access key (equivalent to AWS access key ID). |
| `MINIO_SECRET_KEY` | `minioadmin` | string | MinIO secret key (equivalent to AWS secret access key). |
| `MINIO_SECURE` | `false` | boolean | Use HTTPS for MinIO connections. Set to `true` in production. |
| `MINIO_BUCKET_JUDGMENTS` | `kenya-law-reports` | string | Bucket for ingested and indexed court judgments. |
| `MINIO_BUCKET_UPLOADS` | `court-records-uploads` | string | Bucket for user-uploaded documents awaiting ingestion. |
| `PRESIGNED_URL_EXPIRY_SECONDS` | `900` | integer | Expiry duration for presigned upload URLs (default 15 minutes). |

---

## 8. Ingestion Pipeline Settings

These variables are read by `pipelines/ingestion/main.py` and can be placed in `pipelines/ingestion/.env` for isolated pipeline configuration.

| Environment Variable | Default | Type | Description |
|---|---|---|---|
| `INGESTION_CHUNK_SIZE` | `512` | integer | Target token size for each document chunk. Preserves legal context. |
| `INGESTION_CHUNK_OVERLAP` | `50` | integer | Token overlap between consecutive chunks to maintain cross-chunk context. |
| `INGESTION_BATCH_SIZE` | `16` | integer | Number of chunks processed per batch during embedding and indexing. |
| `INGESTION_MAX_CONCURRENCY` | `4` | integer | Maximum parallel workers for the ingestion pipeline. |
| `INGESTION_LOG_LEVEL` | `INFO` | string | Log level for pipeline workers. |
| `PDF_MAX_PAGES` | `500` | integer | Maximum pages to process from a single PDF document. Pages beyond this limit are skipped. |
| `SUPPORTED_FORMATS` | `pdf,docx,html` | string | Comma-separated list of file extensions the ingestion pipeline accepts. |
| `GRAPH_EXTRACTION_ENABLED` | `true` | boolean | Enable Neo4j citation graph extraction alongside Qdrant indexing. Disable to speed up ingestion during testing. |
| `QDRANT_UPSERT_BATCH_SIZE` | `100` | integer | Number of vectors written to Qdrant per upsert call. |
| `NEO4J_BATCH_SIZE` | `50` | integer | Number of graph nodes/relationships written to Neo4j per transaction. |

Full pipeline configuration is also managed in `pipelines/ingestion/config.yaml`.

---

## 9. Docker Compose Overrides

To customize the Docker Compose setup without modifying `docker-compose.yml`, create a `docker-compose.override.yml` file in the project root. Docker Compose automatically merges it.

### Example: Use a different Ollama port

```yaml
# docker-compose.override.yml
services:
  ollama:
    ports:
      - "11435:11434"
```

### Example: Enable GPU acceleration for Ollama

```yaml
# docker-compose.override.yml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Example: Persist Neo4j data to a custom path

```yaml
# docker-compose.override.yml
services:
  neo4j:
    volumes:
      - /data/sheria/neo4j:/data
```

---

## 10. Production vs Development Settings Comparison

| Setting | Development | Production |
|---|---|---|
| `ENV` | `development` | `production` |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| `LOG_FORMAT` | `text` | `json` |
| `RELOAD` | `true` | `false` |
| `WORKERS` | `1` | `(2 * vCPU) + 1` |
| `DOCS_ENABLED` | `true` | `false` |
| `CORS_ORIGINS` | `*` | `https://sheria.judiciary.go.ke` |
| `HTTPS_ONLY` | `false` | `true` |
| `DB_ECHO` | `true` | `false` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 h) | `60` (1 h) |
| `QDRANT_HOST` | `localhost` | `qdrant.sheria-internal.svc.cluster.local` |
| `NEO4J_URI` | `bolt://localhost:7687` | `neo4j+s://neo4j.sheria-internal.svc.cluster.local:7687` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `http://ollama.sheria-internal.svc.cluster.local:11434` |
| `MINIO_SECURE` | `false` | `true` |
| `MINIO_ENDPOINT` | `localhost:9000` | AWS S3 endpoint or internal MinIO cluster |
| `BCRYPT_ROUNDS` | `10` | `12` |
| `SEMANTIC_CACHE_TTL` | `3600` (1 h) | `86400` (24 h) |

### Production Secrets Management

In Kubernetes production deployments, secrets (`JWT_SECRET_KEY`, `DATABASE_URL`, `NEO4J_PASSWORD`, etc.) are managed via Kubernetes Secrets and mounted as environment variables. Do not store production secrets in `.env` files or commit them to source control.

```bash
# Create Kubernetes secrets
kubectl create secret generic sheria-secrets \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -base64 64)" \
  --from-literal=DATABASE_URL="postgresql://..." \
  --from-literal=NEO4J_PASSWORD="..." \
  -n sheria
```

See `deploy/secrets/` for Kubernetes Secret manifests and `infra/terraform/` for AWS Secrets Manager integration.
