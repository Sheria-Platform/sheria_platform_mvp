# Sheria Platform — Deployment Guide

---

## 1. Docker Compose Service Topology

The full development stack runs 10 services defined in `docker-compose.yml`:

```
┌─────────────────────────────────────────────────────────────────┐
│                    docker-compose network                       │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │PostgreSQL│  │  Redis   │  │  Qdrant  │  │    Neo4j     │   │
│  │  :5432   │  │  :6379   │  │  :6333   │  │:7474 / :7687 │   │
│  │postgres  │  │  redis   │  │  :6334   │  │   neo4j      │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│                                                                 │
│  ┌──────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │  MinIO   │  │       Ollama         │  │  ollama-proxy    │  │
│  │  :9000   │  │       :11434         │  │  :11435-11437    │  │
│  │  :9001   │  │  (LLM + Embeddings)  │  │  (nginx LB)      │  │
│  └──────────┘  └──────────────────────┘  └──────────────────┘  │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │     sheria-api       │  │  mailhog │  │   open-webui     │  │
│  │       :8000          │  │  :1025   │  │     :3030        │  │
│  │  (FastAPI app)       │  │  :8025   │  │  (chat UI dev)   │  │
│  └──────────────────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Service Details

### PostgreSQL
```yaml
image: postgres:15-alpine
ports: ["5432:5432"]
environment:
  POSTGRES_USER: ragadmin
  POSTGRES_PASSWORD: changeme
  POSTGRES_DB: rag_db
volumes:
  - postgres_data:/var/lib/postgresql/data
```
**Health check:** `pg_isready -U ragadmin`

---

### Redis
```yaml
image: redis:7-alpine
ports: ["6379:6379"]
```
**Purpose:** Backing store for semantic cache metadata; available for future hot-path caching.

---

### Qdrant
```yaml
image: qdrant/qdrant:v1.7.3
ports:
  - "6333:6333"   # REST API
  - "6334:6334"   # gRPC (used by application)
volumes:
  - qdrant_data:/qdrant/storage
```
**REST UI:** `http://localhost:6333/dashboard`
**Application uses gRPC (port 6334) for lower latency.**

---

### Neo4j
```yaml
image: neo4j:5.16.0-community
ports:
  - "7474:7474"   # HTTP Browser
  - "7687:7687"   # Bolt protocol
environment:
  NEO4J_AUTH: neo4j/password
  NEO4J_PLUGINS: '["apoc"]'
volumes:
  - neo4j_data:/data
```
**Browser UI:** `http://localhost:7474`

---

### MinIO
```yaml
image: minio/minio
ports:
  - "9000:9000"   # API endpoint (S3-compatible)
  - "9001:9001"   # Web console
environment:
  MINIO_ROOT_USER: minioadmin
  MINIO_ROOT_PASSWORD: minioadmin
command: server /data --console-address ":9001"
```
**Console:** `http://localhost:9001` (login: minioadmin/minioadmin)

---

### Ollama
```yaml
image: ollama/ollama
ports: ["11434:11434"]
volumes:
  - ollama_data:/root/.ollama
```

**Pull required models after startup:**
```bash
docker exec -it ollama ollama pull llama3.3
docker exec -it ollama ollama pull nomic-embed-text
```

**Non-standard port:** The application is configured with `OLLAMA_BASE_URL=http://ollama:11434` (standard Ollama port 11434, not 11433 as in older memory notes).

---

### Ollama Proxy
```yaml
image: nginx:alpine
ports:
  - "11435:11435"
  - "11436:11436"
  - "11437:11437"
```
**Purpose:** Load balancer across multiple Ollama instances for production scaling.

---

### Sheria API
```yaml
build:
  context: .
  dockerfile: services/api/Dockerfile
ports: ["8000:8000"]
depends_on:
  - postgres
  - redis
  - qdrant
  - neo4j
  - ollama
environment:
  DATABASE_URL: postgresql+asyncpg://ragadmin:changeme@postgres:5432/rag_db
  REDIS_URL: redis://redis:6379
  QDRANT_HOST: qdrant
  QDRANT_PORT: 6333
  NEO4J_URI: bolt://neo4j:7687
  OLLAMA_BASE_URL: http://ollama:11434
```

---

### MailHog
```yaml
image: mailhog/mailhog:v1.0.1
ports:
  - "1025:1025"   # SMTP server
  - "8025:8025"   # Web UI
```
**Web UI:** `http://localhost:8025` (captures all outgoing emails in development)

**API config for dev:**
```env
SMTP_HOST=mailhog
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
```

---

### Open WebUI
```yaml
image: ghcr.io/open-webui/open-webui:main
ports: ["3030:8080"]
environment:
  OLLAMA_BASE_URL: http://ollama:11434
  WEBUI_SECRET_KEY: <generated>
```
**URL:** `http://localhost:3030`

---

## 3. Environment Configuration

Copy `.env.example` to `.env` before starting:

```bash
cp .env.example .env
```

### Minimum Required Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://ragadmin:changeme@localhost:5432/rag_db

# Security
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Redis
REDIS_URL=redis://localhost:6379

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=kenya_law_reports

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.3
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# MinIO (for presigned URLs)
MINIO_SERVER_URL=http://localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
S3_BUCKET_NAME=court-records-dev

# Admin Seed
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@judiciary.go.ke
ADMIN_PASSWORD=Admin1234!

# Email (dev: MailHog)
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@judiciary.go.ke
APP_BASE_URL=http://localhost:3000
```

---

## 4. Startup Sequence

### Quick Start

```bash
# 1. Clone and set up environment
cp .env.example .env
# Edit .env with your values

# 2. Start all infrastructure services
make up
# or: docker compose up -d

# 3. Wait for services (check health)
docker compose ps

# 4. Pull Ollama models (first time only, takes ~10 minutes)
docker exec -it ollama ollama pull llama3.3
docker exec -it ollama ollama pull nomic-embed-text

# 5. Start API server with hot reload
make dev
# or: uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env

# 6. Start frontend (in separate terminal)
cd user_interface && npm install && npm run dev
```

### Verify Startup

```bash
# API health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","services":{"postgres":"connected","redis":"connected",...}}

# Check admin account was seeded
# Login with admin credentials from .env
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234!"}'
```

---

## 5. Service Dependencies

```
sheria-api
  ├── postgres (REQUIRED: tables + user storage)
  ├── redis (REQUIRED: cache)
  ├── qdrant (REQUIRED: vector search + semantic cache)
  ├── neo4j (REQUIRED: graph search)
  └── ollama (REQUIRED: LLM + embeddings)
        └── [models: llama3.3, nomic-embed-text]

open-webui
  └── ollama (optional integration)

ingestion pipeline (separate process)
  ├── minio (source documents)
  ├── qdrant (vector indexing)
  └── neo4j (graph indexing)
```

---

## 6. Data Volume Management

```yaml
volumes:
  postgres_data:     # User accounts, chat history, feedback
  redis_data:        # Cache data (optional persistence)
  qdrant_data:       # Kenya Law Reports embeddings + semantic cache
  neo4j_data:        # Citation graph
  minio_data:        # Court document PDFs
  ollama_data:       # Downloaded model weights (~8-70GB depending on model)
```

**Storage estimates for production:**
| Volume | Estimated Size |
|--------|---------------|
| `postgres_data` | 1-10 GB |
| `qdrant_data` | 5-20 GB (depends on corpus size) |
| `neo4j_data` | 1-5 GB |
| `minio_data` | 10-500 GB (court documents) |
| `ollama_data` | 8 GB (llama3.3) + 0.5 GB (nomic-embed-text) |

---

## 7. Makefile Commands Reference

```bash
make install     # Install Python dependencies (pip install -r requirements.txt)
make up          # Start Docker Compose services (docker compose up -d)
make down        # Stop Docker Compose services
make dev         # Start FastAPI with hot reload
make test        # Run pytest test suite
make infra       # Apply Terraform infrastructure (AWS)
make deploy      # Deploy to Kubernetes (EKS)
```

---

## 8. Production Deployment Checklist

- [ ] Generate strong `JWT_SECRET_KEY` (minimum 32 random bytes)
- [ ] Change `ADMIN_PASSWORD` from default `Admin1234!`
- [ ] Set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (MailHog is dev-only)
- [ ] Set `APP_BASE_URL` to production domain
- [ ] Configure `ALLOWED_ORIGINS` for CORS (currently hardcoded to `localhost:3000`)
- [ ] Use PostgreSQL with SSL (`DATABASE_URL` with `?ssl=require`)
- [ ] Configure Qdrant with authentication
- [ ] Deploy Ollama on GPU instance for acceptable inference latency
- [ ] Set `LOG_LEVEL=WARNING` or `ERROR` for production
- [ ] Configure Prometheus scrape target for `/metrics`
- [ ] Review and rotate all default credentials in `docker-compose.yml`
- [ ] Enable Neo4j authentication (default `neo4j/password` is insecure)
- [ ] MinIO: change `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from defaults
