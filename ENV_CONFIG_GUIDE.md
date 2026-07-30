# Environment Configuration Guide

## Overview

All Sheria Platform configuration is now centralized in `.env` for uniformity and ease of management. The `docker-compose.yml` file references these environment variables with sensible defaults.

## Quick Setup

```bash
# 1. Copy the example file
cp .env.example .env

# 2. Generate secure keys
openssl rand -base64 32  # For JWT_SECRET_KEY
openssl rand -base64 32  # For WEBUI_SECRET_KEY

# 3. Edit .env with your values
nano .env

# 4. Start services (will automatically use .env)
docker-compose up -d
```

---

## Configuration Sections

### 1. Application Settings

```bash
ENV=dev                    # Environment: dev, staging, prod
LOG_LEVEL=INFO            # Logging level: DEBUG, INFO, WARN, ERROR
JWT_SECRET_KEY=...        # Secret for JWT token signing
```

---

### 2. PostgreSQL Database

**Purpose:** Stores case metadata, judicial decisions history, user profiles

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ragadmin
POSTGRES_PASSWORD=changeme
POSTGRES_DB=rag_db
DATABASE_URL=postgresql+asyncpg://ragadmin:changeme@localhost:5432/rag_db
```

**Access:**
- **Docker service**: `postgres`
- **Web UI**: Use pgAdmin or DBeaver
- **CLI**: `psql -h localhost -U ragadmin -d rag_db`

---

### 3. Redis Cache

**Purpose:** Semantic cache for legal research queries, session storage

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://localhost:6379/0
```

**Access:**
- **Docker service**: `redis`
- **CLI**: `redis-cli -h localhost -p 6379`
- **Test**: `redis-cli ping` (should return PONG)

---

### 4. Qdrant (Vector Database)

**Purpose:** Stores embeddings for Kenya Law Reports, enables semantic search

```bash
QDRANT_HOST=localhost
QDRANT_PORT=6333          # REST API
QDRANT_GRPC_PORT=6334     # gRPC
QDRANT_COLLECTION=kenya_law_reports
QDRANT_IMAGE=qdrant/qdrant:v1.7.3
```

**Access:**
- **Docker service**: `qdrant`
- **Web UI**: http://localhost:6333/dashboard
- **API**: `curl http://localhost:6333/collections/kenya_law_reports`

---

### 5. Neo4j (Graph Database)

**Purpose:** Citation graph, legal principle relationships, case connections

```bash
NEO4J_HOST=localhost
NEO4J_HTTP_PORT=7474      # Neo4j Browser
NEO4J_BOLT_PORT=7687      # Bolt protocol
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_AUTH=neo4j/password
NEO4J_URI=bolt://localhost:7687
NEO4J_MEMORY_PAGECACHE_SIZE=1G
NEO4J_IMAGE=neo4j:5.16.0-community
```

**Access:**
- **Docker service**: `neo4j`
- **Web UI**: http://localhost:7474
- **Cypher Shell**: `docker exec -it sheria-neo4j cypher-shell -u neo4j -p password`

**Example Query:**
```cypher
// Show all cases
MATCH (n:Case) RETURN n LIMIT 25

// Show citation relationships
MATCH (a:Case)-[r:CITES]->(b:Case) RETURN a, r, b LIMIT 10
```

---

### 6. MinIO (Object Storage)

**Purpose:** S3-compatible storage for court documents, Kenya Law Reports PDFs

```bash
MINIO_HOST=localhost
MINIO_PORT=9000           # API
MINIO_CONSOLE_PORT=9001   # Web console
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BROWSER_REDIRECT_URL=http://localhost:9001
MINIO_SERVER_URL=http://localhost:9000

# Buckets
MINIO_BUCKET_COURT_RECORDS=court-records-dev
MINIO_BUCKET_KENYA_LAW=kenya-law-reports-dev
MINIO_BUCKET_CASE_FILES=case-files-dev
```

**Access:**
- **Docker service**: `minio`
- **Web Console**: http://localhost:9001
- **API**: http://localhost:9000
- **AWS CLI**: Configure with `aws configure` using minioadmin credentials

**Create Buckets:**
```bash
# Using MinIO Client (mc)
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/kenya-law-reports-dev
mc mb local/court-records-dev
mc mb local/case-files-dev
```

---

### 7. Ollama (Local LLM)

**Purpose:** Embeddings generation and graph extraction for ingestion pipeline

```bash
OLLAMA_HOST=http://localhost:11434
OLLAMA_PORT=11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=qwen3:8b
COMPOSE_PROFILES=cpu     # "cpu" (default, no GPU) or "gpu" (requires nvidia-container-toolkit)
OLLAMA_NUM_GPU=all       # only used when COMPOSE_PROFILES=gpu — GPU device count
```

**GPU vs CPU:**
- Default is CPU-only (`COMPOSE_PROFILES=cpu`) — works on any machine, no NVIDIA drivers required.
- To use a GPU: set `COMPOSE_PROFILES=gpu` in `.env`, ensure `nvidia-container-toolkit` is installed on the Docker host, then run `make up` as usual — Compose reads `COMPOSE_PROFILES` from `.env` automatically, no `--profile` flag needed.
- Do not rely on `OLLAMA_NUM_GPU=0` to "disable" GPU use — the old approach (setting the device `count` to 0 while still declaring `driver: nvidia` unconditionally) still required Docker to resolve the nvidia driver at container-creation time, and fails with `could not select device driver "" with capabilities: [[gpu]]` on machines without the NVIDIA Container Toolkit. `COMPOSE_PROFILES=cpu` avoids the device reservation being declared at all.

**Access:**
- **Docker service**: `ollama` (DNS alias shared by both the `ollama`/gpu and `ollama-cpu`/cpu variants)
- **API**: `curl http://localhost:11434/api/tags`
- **Pull models**: `ollama pull nomic-embed-text`

**Required Models:**
```bash
# Embedding model (required for ingestion)
ollama pull nomic-embed-text

# LLM for graph extraction (required for ingestion; shared with services/api)
ollama pull qwen3:8b

# Optional: Better embeddings
ollama pull mxbai-embed-large

# Optional: Larger LLM
ollama pull llama3.1
```

---

### 8. Open WebUI

**Purpose:** Web interface for testing legal research, prototype judge interface

```bash
OPEN_WEBUI_PORT=3030
WEBUI_SECRET_KEY=...      # Generate with: openssl rand -base64 32
ENABLE_SIGNUP=true
DEFAULT_USER_ROLE=user
ENABLE_RAG=true
RAG_EMBEDDING_ENGINE=ollama
RAG_EMBEDDING_MODEL=nomic-embed-text
ENABLE_WEB_SEARCH=false
WEBUI_NAME=Sheria Legal Research
WEBUI_AUTH=true
```

**Access:**
- **Docker service**: `open-webui`
- **Web UI**: http://localhost:3030
- **First login**: Create admin account on first visit

---

### 9. Ingestion Pipeline Settings

```bash
# Chunking
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Batch sizes
EMBEDDING_BATCH_SIZE=100
GRAPH_EXTRACTION_BATCH_SIZE=5

# Concurrency
EMBEDDING_CONCURRENCY=5
GRAPH_EXTRACTION_CONCURRENCY=10
```

**Usage:** These settings are automatically picked up by `pipelines/ingestion/main.py`

---

### 10. External API Integrations (Judiciary)

**For Production:** Integrate with Kenya government APIs

```bash
# Law Society of Kenya (advocate verification)
LSK_API_KEY=
LSK_API_URL=https://api.lsk.or.ke/v1

# Ministry of Lands (title deed verification)
LANDS_REGISTRY_API_KEY=
LANDS_REGISTRY_API_URL=https://api.lands.go.ke/v1

# Civil Registration Services (certificates)
CIVIL_REGISTRATION_API_KEY=
CIVIL_REGISTRATION_API_URL=https://api.crs.go.ke/v1

# Judiciary Case Management System
JUDICIARY_CMS_API_KEY=
JUDICIARY_CMS_API_URL=https://api.judiciary.go.ke/v1
```

**Note:** These are for production deployment. Leave empty for local development.

---

### 11. AWS (Production Infrastructure)

```bash
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Production S3 buckets
S3_BUCKET_COURT_RECORDS=sheria-court-records-prod
S3_BUCKET_KENYA_LAW=kenya-law-reports-prod
S3_BUCKET_CASE_FILES=case-files-prod
```

---

### 12. Security & Authentication

```bash
# JWT Configuration
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
CORS_ALLOW_CREDENTIALS=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
```

---

### 13. Observability & Monitoring

```bash
# OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Logging
LOG_FORMAT=json
LOG_FILE_PATH=./logs/sheria.log

# Metrics
ENABLE_METRICS=true
METRICS_PORT=9090

# Tracing
ENABLE_TRACING=true
JAEGER_AGENT_HOST=localhost
JAEGER_AGENT_PORT=6831
```

---

### 14. Feature Flags

```bash
ENABLE_DOCUMENT_VERIFICATION=true
ENABLE_GRAPH_EXTRACTION=true
ENABLE_SEMANTIC_CACHE=true
ENABLE_WORKLOAD_ANALYTICS=false  # Coming soon
```

---

## Environment-Specific Configuration

### Development (.env.dev)
```bash
ENV=dev
LOG_LEVEL=DEBUG
ENABLE_SIGNUP=true
RATE_LIMIT_ENABLED=false
```

### Staging (.env.staging)
```bash
ENV=staging
LOG_LEVEL=INFO
ENABLE_SIGNUP=false
RATE_LIMIT_ENABLED=true
```

### Production (.env.prod)
```bash
ENV=prod
LOG_LEVEL=WARN
ENABLE_SIGNUP=false
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=30
# Use AWS S3 instead of MinIO
# Use hosted databases instead of Docker
```

---

## Override Precedence

The configuration follows this precedence (highest to lowest):

1. **Command-line arguments**
2. **Environment variables** (from shell or .env)
3. **docker-compose.yml defaults** (using `${VAR:-default}`)
4. **Application defaults** (in code)

**Example:**
```bash
# Override in docker-compose up
POSTGRES_PORT=5433 docker-compose up -d postgres

# Override in .env
POSTGRES_PORT=5433
```

---

## Validation

### Check Configuration

```bash
# Show all environment variables
docker-compose config

# Test database connections
docker-compose up -d
docker-compose ps

# Check service health
docker-compose ps | grep "healthy"
```

### Verify Services

```bash
# PostgreSQL
psql -h localhost -U ragadmin -d rag_db -c "SELECT 1"

# Redis
redis-cli ping

# Qdrant
curl http://localhost:6333/healthz

# Neo4j
curl http://localhost:7474

# MinIO
curl http://localhost:9000/minio/health/live

# Ollama
curl http://localhost:11434/api/tags
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs <service_name>

# Example
docker-compose logs postgres
docker-compose logs ollama
```

### Port Already in Use

```bash
# Find process using port
lsof -i :5432

# Kill process (macOS/Linux)
kill -9 <PID>

# Or change port in .env
POSTGRES_PORT=5433
```

### Environment Variable Not Working

```bash
# Verify .env is being read
docker-compose config | grep POSTGRES_PORT

# Recreate containers to pick up new env vars
docker-compose down
docker-compose up -d
```

### Reset Everything

```bash
# Stop and remove all containers, volumes, networks
docker-compose down -v

# Start fresh
docker-compose up -d
```

---

## Best Practices

### Security

1. **Never commit .env to git**
   - `.env` is in `.gitignore`
   - Use `.env.example` as template

2. **Generate secure secrets**
   ```bash
   openssl rand -base64 32  # For JWT_SECRET_KEY
   openssl rand -hex 32     # For API keys
   ```

3. **Use strong passwords**
   - Especially for production databases
   - Rotate credentials regularly

### Development

1. **Use .env for local overrides**
   ```bash
   # .env (not committed)
   POSTGRES_PASSWORD=my_local_password
   ```

2. **Keep .env.example updated**
   - Document all new variables
   - Provide sensible defaults

3. **Test with docker-compose config**
   ```bash
   docker-compose config  # Shows resolved configuration
   ```

---

## Migration from Old Configuration

If migrating from hardcoded values:

```bash
# Old (hardcoded in docker-compose.yml)
POSTGRES_PASSWORD: changeme

# New (environment variable with default)
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
```

**Migration Steps:**

1. Copy `.env.example` to `.env`
2. Update any values you want to change
3. Run `docker-compose down -v` to remove old volumes (if needed)
4. Run `docker-compose up -d` with new configuration

---

## Reference

- **docker-compose.yml**: Service definitions with env var references
- **.env.example**: Template with all available settings
- **.env**: Your local configuration (git-ignored)

For more details, see:
- [Docker Compose Environment Variables](https://docs.docker.com/compose/environment-variables/)
- [12-Factor App Config](https://12factor.net/config)

---

## Support

For configuration issues:
- GitHub Issues: https://github.com/sheria-platform/judicial-mvp/issues
- Documentation: See CLAUDE.md and pipeline READMEs
