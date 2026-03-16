# Sheria Platform MVP — Implementation Review Documentation

> **Purpose:** This document set is generated for PR review of the Sheria Platform MVP codebase. It covers the implemented architecture, workflows, API contracts, data models, security posture, and deployment topology.

---

## Document Index

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | This file — overview and navigation |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, component design, data flows |
| [API_REFERENCE.md](API_REFERENCE.md) | All API endpoints, request/response shapes, auth contracts |
| [DATA_MODEL.md](DATA_MODEL.md) | Database schemas, ORM models, vector/graph data structures |
| [SECURITY.md](SECURITY.md) | Authentication flows, authorization model, security controls |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Docker Compose topology, environment config, startup sequence |
| [BPMN_WORKFLOWS.md](BPMN_WORKFLOWS.md) | Business process flows (BPMN 2.0 + Mermaid diagrams) |
| [AGENT_DESIGN.md](AGENT_DESIGN.md) | LangGraph agent internals — state machine, node logic, routing |

---

## What Was Built

The Sheria Platform MVP is an **AI-powered judicial intelligence platform** for Kenya's court system. It provides conversational legal research over Kenya Law Reports using a hybrid RAG pipeline (Vector + Graph retrieval), a supervised user registration workflow, document upload to S3-compatible storage, and an admin dashboard.

### Core Capabilities Implemented

| Capability | Status | Key Files |
|-----------|--------|-----------|
| Agentic RAG Chat (streaming) | Implemented | `routes/chat.py`, `agents/` |
| Hybrid Retrieval (Qdrant + Neo4j) | Implemented | `agents/nodes/retriever.py` |
| Semantic Cache (30-day TTL) | Implemented | `cache/semantic.py` |
| Supervised User Registration | Implemented | `routes/auth.py` |
| JWT Authentication | Implemented | `auth/jwt.py` |
| Async Activation Email | Implemented | `utils/email.py` |
| Document Upload (Presigned URL) | Implemented | `routes/upload.py` |
| Conversation History | Implemented | `routes/history.py`, `memory/postgres.py` |
| User Feedback (ratings) | Implemented | `routes/feedback.py` |
| Admin: suspend/reactivate users | Implemented | `routes/auth.py` |
| Prometheus Observability | Implemented | `libs/observability/metrics.py` |
| Structured JSON Logging | Implemented | `app/logging.py` |
| Ingestion Pipeline (Ray Data) | Implemented | `pipelines/ingestion/` |
| Next.js Frontend | Implemented | `user_interface/` |
| Default Admin Seed on Boot | Implemented | `memory/postgres.py` |
| Document Verification (Sheria Verify) | Implemented | `routes/verify.py`, `tools/verify_document.py` |
| Structured Legal Research (Sheria Ask) | Implemented | `routes/legal_research.py`, `agents/legal_research_graph.py` |
| Verification History | Implemented | `memory/postgres.py` (`verification_activity` table) |

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| API Framework | FastAPI | Latest |
| LLM Inference | Ollama + llama3.3 | — |
| Embedding Model | nomic-embed-text (768-dim) | — |
| Agent Orchestration | LangGraph | — |
| Vector DB | Qdrant | v1.7.3 |
| Graph DB | Neo4j | 5.16.0-community |
| Relational DB | PostgreSQL + asyncpg | 15 |
| Cache | Redis | 7 |
| Object Storage | MinIO (S3-compatible) | — |
| Frontend | Next.js + TypeScript + Tailwind | — |
| Ingestion | Ray Data | — |
| Container Runtime | Docker Compose | — |
| Email (Dev) | MailHog | v1.0.1 |
| Metrics | Prometheus (via prometheus-client) | — |

---

## Branch Under Review

**Branch:** `sheria-verify-basic-design`
**Base:** `main`

### Recent Commits on This Branch

```
e821acd  feat(ui): update branding and implement collapsible sidebar
c0f0e69  feat(history): add ingestion jobs and verification tabs to history page
cede39f  feat(memory): add verification activity model and persistence methods
b864a30  feat(verify): add document verification page with file upload and form
5f4ebc4  chore(docs): update ReadMe.md and regenerate secrets baseline
```

---

## Key Reviewer Checkpoints

When reviewing this PR, focus on:

1. **Auth flow correctness** — Registration → Admin approval → Email → Activation → Login → JWT
2. **Semantic cache reliability** — Cache hit/miss logic, TTL enforcement, vector reuse
3. **Agent routing logic** — Planner action routing (`retrieve` / `direct_answer` / `tool_use`)
4. **Hybrid RAG deduplication** — Vector + graph results are deduplicated by content
5. **Async email fire-and-forget** — Does it fail silently? What happens on SMTP error?
6. **Admin seed idempotency** — Called every startup; must not duplicate admin
7. **Session ownership** — History endpoints must reject cross-user access
8. **ORM migration** — Feedback table migrated from raw SQL to ORM; data compatibility
9. **Presigned URL TTL** — 1-hour window for S3 uploads; adequate for large files?
10. **Database pool config** — `pool_size=10, max_overflow=20`; adequate for load?
11. **Embedding dimension** — `_EMBEDDING_DIM = 768` in `main.py` creates the `semantic_cache` Qdrant collection; confirm this matches the actual output dimension of `nomic-embed-text` in the Ollama version deployed
12. **Verify pipeline resilience** — `verify_document` tool runs LLM + Qdrant in sequence; confirm graceful degradation for scanned/image-only PDFs (empty text path) and Qdrant unavailability
