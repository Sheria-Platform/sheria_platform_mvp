# Sheria Platform — Implementation Plan

> **Branch:** `sheria-verify-basic-design` → `main`
> **Generated:** 2026-03-16
> **Based on:** Review of `docs/review/` evaluation findings against live codebase

This document translates every evaluation finding into discrete, executable tasks grouped by phase and priority. Tasks are ordered by dependency — later phases assume earlier ones are complete.

---

## How to read this plan

| Symbol | Meaning |
|--------|---------|
| 🔴 | Blocks PR merge — must be done before merging this branch |
| 🟡 | Next sprint — security or correctness gap, not a merge blocker |
| 🟢 | Backlog — feature or tech-debt, no urgency |
| `file:line` | Exact location in the codebase to modify |

---

## Phase 1 — Pre-merge fixes (branch: `sheria-verify-basic-design`)

These must be resolved before this branch is merged into `main`.

---

### 1.1 Resolve embedding dimension 🟢

**Problem:** `main.py:58` creates the `semantic_cache` Qdrant collection with `_EMBEDDING_DIM = 768`.
All prior code and the ingestion pipeline assumed `2560` (nomic-embed-text).
If the actual model output is `2560`, every vector insert and search against `semantic_cache` silently fails.

**Tasks:**

- [x] **1.1.1** — Confirm the actual output dimension of `nomic-embed-text` in the running Ollama instance:
  ```bash
  docker exec -it ollama ollama show nomic-embed-text --modelinfo | grep "embedding length"
  ```
  Expected result: either `768` or `2560`. Note the value.

- [x] **1.1.2** — If actual dimension is `2560`, update `main.py:58`:
  ```python
  # services/api/main.py
  _EMBEDDING_DIM = 2560   # was 768 — corrected to match nomic-embed-text actual output
  ```
  Drop and recreate the `semantic_cache` collection (it will be empty in dev — safe to recreate).

- [x] **1.1.3** — If actual dimension is `768`, confirm the ingestion pipeline's Qdrant indexing step
  (`pipelines/ingestion/indexing/qdrant_indexing.py`) also uses `768` when creating the
  `kenya_law_reports` collection. Both collections must use the same dimension as the model output.

- [x] **1.1.4** — Add a startup assertion in `_ensure_qdrant_collections()` (`main.py:114`) that
  verifies the existing `kenya_law_reports` collection dimension matches `_EMBEDDING_DIM`, and logs
  a clear error (not a silent mismatch) if they differ.

---

### 1.2 Fix CORS — remove hardcoded LAN IP 🟢

**Problem:** `main.py:240-248` hardcodes `192.168.100.104` — a specific developer's LAN address.
This breaks in every other environment and must not reach staging or production.

**Tasks:**

- [x] **1.2.1** — Add `ALLOWED_ORIGINS` to `services/api/app/config.py` (`Settings` class):
  ```python
  # services/api/app/config.py
  ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
  ```

- [x] **1.2.2** — Update `main.py:238-249` to read from settings:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.ALLOWED_ORIGINS.split(","),
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- [x] **1.2.3** — Add `ALLOWED_ORIGINS` to `.env.example` with the dev default:
  ```env
  ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
  ```

- [x] **1.2.4** — Add `ALLOWED_ORIGINS` to the `sheria-api` service `environment:` block in
  `docker-compose.yml`.

---

### 1.3 Add PDF upload size limit to the verify endpoint 🟢

**Problem:** `routes/verify.py:139` calls `await file.read()` with no size guard. A malformed
multi-GB PDF (or a deliberate OOM attack) will exhaust container memory.

**Tasks:**

- [x] **1.3.1** — Add a size check immediately after `pdf_bytes = await file.read()` in
  `routes/verify.py:139`. Reject files larger than 20 MB (configurable):
  ```python
  MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
  if len(pdf_bytes) > MAX_PDF_BYTES:
      raise HTTPException(
          status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
          detail=f"File too large. Maximum size is {MAX_PDF_BYTES // 1_048_576} MB.",
      )
  ```

- [x] **1.3.2** — Add `MAX_PDF_UPLOAD_MB: int = 20` to `config.py` so the limit is configurable
  via environment variable without code changes.

- [x] **1.3.3** — Document the limit in `API_REFERENCE.md` under `POST /api/v1/verify`.

---

### 1.4 Confirm `approved_by` is surfaced in admin responses 🟢

**Status:** `approved_by` is correctly written in `auth.py:225` (`approved_by=admin["id"]`).
The column is populated. Remaining gap: the admin user-list response strips it.

**Tasks:**

- [x] **1.4.1** — Audit `auth.py:258-261` (`list_users` handler). The current strip list only
  removes `hashed_password` and `activation_token`. Confirm `approved_by` is **included** in the
  response (it should be — just verify it is not accidentally excluded).

- [x] **1.4.2** — Add `approved_by` to the user object in `API_REFERENCE.md` under
  `GET /api/v1/auth/users` response schema.

---

## Phase 2 — Data population (enables core RAG)

The `kenya_law_reports` Qdrant collection is empty. Until it has documents, the legal research
and chat endpoints return hollow AI responses. This is the highest-impact unblocking task.

---

### 2.1 Run the data scraper 🟡

- [ ] **2.1.1** — Review and run `data_scrapper/data_scrapper.py` targeting Kenya Law Reports
  (Supreme Court, Court of Appeal, High Court). Verify output lands in `kenya_law_data/`.

- [ ] **2.1.2** — Validate scraped files: count PDFs/HTMLs, spot-check 3-5 documents for
  readable text (not image-only scans).

- [ ] **2.1.3** — Document the scraper run in a `data_scrapper/README.md`: target URL, date run,
  counts, any known gaps.

---

### 2.2 Upload to MinIO and trigger ingestion 🟡

- [ ] **2.2.1** — Start the full Docker Compose stack (`make up`). Confirm all 10 services healthy:
  ```bash
  curl http://localhost:8000/health
  ```

- [ ] **2.2.2** — Run the ingestion script:
  ```bash
  python testExample/minio_ingestion.py
  ```
  Monitor logs for chunk counts, embedding counts, and Neo4j node creation.

- [ ] **2.2.3** — Verify data landed in Qdrant:
  ```bash
  curl http://localhost:6333/collections/kenya_law_reports
  # Check "vectors_count" > 0
  ```

- [ ] **2.2.4** — Verify data landed in Neo4j. Open `http://localhost:7474` and run:
  ```cypher
  MATCH (c:Case) RETURN count(c)
  ```

---

### 2.3 Smoke-test the RAG pipeline 🟡

- [ ] **2.3.1** — Login as admin, send a legal research query, assert non-empty `citations` in
  the response:
  ```bash
  curl -X POST http://localhost:8000/api/v1/legal-research \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is the test for adverse possession in Kenya?"}'
  ```
  Expected: `citations` list is non-empty; `content` references real case citations.

- [ ] **2.3.2** — Test the chat endpoint against the populated corpus:
  ```bash
  curl -X POST http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"message": "Explain vicarious liability in Kenyan case law", "session_id": "test-001"}'
  ```

- [ ] **2.3.3** — Test jurisdiction filter: send a legal research query with
  `"jurisdiction": ["Supreme Court"]` and confirm results only contain Supreme Court cases.

---

## Phase 3 — Security hardening

Three gaps flagged in the security checklist are genuine vulnerabilities that must be closed
before any shared or staging deployment.

---

### 3.1 Rate-limit the login endpoint 🟡

**Problem:** `POST /api/v1/auth/login` has no brute-force protection. An attacker can enumerate
passwords without throttling.

**Tasks:**

- [ ] **3.1.1** — Add `slowapi` to `pyproject.toml` / `requirements.txt`:
  ```
  slowapi>=0.1.9
  ```

- [ ] **3.1.2** — Configure a `Limiter` in `main.py` backed by the existing Redis client:
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address
  limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
  app.state.limiter = limiter
  ```

- [ ] **3.1.3** — Apply the decorator to `auth.py:127` (`login` handler):
  ```python
  @router.post("/login")
  @limiter.limit("5/15minutes")
  async def login(request: Request, req: LoginRequest) -> dict:
  ```
  Return `429 Too Many Requests` on breach.

- [ ] **3.1.4** — Test: send 6 login attempts in < 15 minutes from the same IP; assert the 6th
  returns `429`.

---

### 3.2 Token revocation for suspended users 🟡

**Problem:** When an admin suspends a user via `POST /auth/users/{id}/status`, the user's existing
JWT remains valid for up to 8 hours. A suspended user can continue making API calls until
their token naturally expires.

**Tasks:**

- [ ] **3.2.1** — Add a `TOKEN_BLACKLIST_TTL_SECONDS: int = 28800` (8 hours) setting to
  `config.py` (matches JWT TTL).

- [ ] **3.2.2** — Create `services/api/app/auth/blacklist.py`:
  ```python
  """Redis-backed JWT blacklist for immediately invalidating tokens."""
  async def blacklist_token(redis_client, jti: str, ttl_seconds: int) -> None: ...
  async def is_blacklisted(redis_client, jti: str) -> bool: ...
  ```

- [ ] **3.2.3** — Add `jti` (JWT ID, a UUID) to the token payload in `auth.py:43`
  (`_create_token`). This gives each token a unique identifier for blacklisting.

- [ ] **3.2.4** — In `auth.py:264` (`update_user_status` → suspend action): after updating DB
  status, look up the user's active token JTI (from a new `active_jti` column on `users`, or from
  a Redis key `user:{user_id}:jti` written at login time) and call `blacklist_token(jti)`.

- [ ] **3.2.5** — In `auth/jwt.py` (`get_current_user`): after decoding the token, call
  `is_blacklisted(jti)`. If blacklisted, raise `HTTPException(401, "Token revoked")`.

- [ ] **3.2.6** — Test: login as a user, get token, admin suspends user, attempt API call with
  old token → assert `401 Token revoked` (not `403`).

---

### 3.3 Activation token expiry 🟡

**Problem:** `auth.py:187` (`activate` handler) looks up a user by `activation_token` but never
checks whether the token was issued recently. A token is valid indefinitely until used.

**Tasks:**

- [ ] **3.3.1** — Add `activation_token_expires_at = Column(DateTime, nullable=True)` to the
  `User` ORM model in `memory/postgres.py`.

- [ ] **3.3.2** — In `memory/postgres.py` (`approve_user` method): set
  `activation_token_expires_at = datetime.utcnow() + timedelta(days=7)` when generating the token.

- [ ] **3.3.3** — In `auth.py:187` (`activate` handler): after retrieving the user by token,
  check `user["activation_token_expires_at"] < datetime.utcnow()`. If expired, raise
  `HTTPException(400, "Activation link has expired. Please contact your administrator.")`.

- [ ] **3.3.4** — Add `ACTIVATION_TOKEN_TTL_DAYS: int = 7` to `config.py`.

- [ ] **3.3.5** — Test: generate an activation token, manually set its expiry to the past in the
  DB, attempt activation → assert `400 Activation link has expired`.

---

## Phase 4 — Test coverage for new features

Existing tests cover: planner, retriever, responder, semantic cache, postgres pool.
Nothing covers the two features added in this branch or the auth flow end-to-end.

---

### 4.1 Unit tests for the verify document tool 🟡

**File:** `tests/unit/test_verify_document.py`

- [ ] **4.1.1** — Test: valid PDF text → pipeline runs all 3 steps → returns authentic=True with
  confidence > 0. Mock `ollama_client` and `qdrant_client`.

- [ ] **4.1.2** — Test: empty text (scanned/image PDF) → pipeline completes without raising →
  authentic field is present in result (may be False with low confidence).

- [ ] **4.1.3** — Test: Ollama returns malformed JSON → `verify_document` returns an error dict
  (not an unhandled exception).

- [ ] **4.1.4** — Test: Qdrant search returns zero results for the case number → verification
  continues and marks `case_cross_reference` check as `passed=False`.

---

### 4.2 Integration test for the verify route 🟡

**File:** `tests/integration/test_verify_route.py`

- [ ] **4.2.1** — Test `POST /api/v1/verify`: upload a real small PDF (`test_data/`), assert
  response shape matches `VerificationReport` schema (all required fields present).

- [ ] **4.2.2** — Test: upload empty bytes → assert `400 Uploaded file is empty`.

- [ ] **4.2.3** — Test: upload a non-PDF file (e.g. plain text with `.pdf` extension) → assert
  `400 Could not parse PDF`.

- [ ] **4.2.4** — Test: upload a PDF exceeding `MAX_PDF_UPLOAD_MB` → assert `413`.

- [ ] **4.2.5** — Test `GET /api/v1/verify/history`: call verify once, then call history → assert
  the record appears with matching `filename`, `authentic`, `confidence`.

- [ ] **4.2.6** — Test: call history without a JWT → assert `401`.

---

### 4.3 Unit tests for the legal research graph 🟡

**File:** `tests/unit/test_legal_research_graph.py`

- [ ] **4.3.1** — Test: `jurisdiction_filter=["Supreme Court"]` → Qdrant search is called with a
  payload filter restricting `court` to `"Supreme Court"`. Mock `qdrant_client.search`.

- [ ] **4.3.2** — Test: `jurisdiction_filter=[]` (no filter) → Qdrant search is called with
  `query_filter=None`.

- [ ] **4.3.3** — Test: retriever node populates `state["citations"]` with the correct structure
  (`text`, `source`, `case_number`, `court`) from Qdrant result payloads.

- [ ] **4.3.4** — Test: responder node emits `citations` in the final answer dict.

---

### 4.4 Integration test for the full auth workflow 🟡

**File:** `tests/integration/test_auth_flow.py`

- [ ] **4.4.1** — Test: `POST /register` → `201` with pending message.

- [ ] **4.4.2** — Test: `POST /login` with `status=pending` → `403 Account pending administrator
  approval`.

- [ ] **4.4.3** — Test: admin calls `POST /approve/{user_id}` → `200`, `activation_token` in
  response.

- [ ] **4.4.4** — Test: `POST /activate` with valid token and mismatched passwords → `400`.

- [ ] **4.4.5** — Test: `POST /activate` with valid token and matching passwords → `200 Account
  activated`.

- [ ] **4.4.6** — Test: `POST /login` after activation → `200` with valid JWT.

- [ ] **4.4.7** — Test: admin calls `POST /users/{id}/status` with `action=suspend` → `200`.
  Then call any authenticated endpoint with the old token → `401` (after Phase 3.2 is implemented).

---

## Phase 5 — Sheria Predict module

With Sheria Digitize, Sheria Verify, and Sheria Ask all functional, the fourth module completes
the platform.

---

### 5.1 Implement `predict_case_duration` tool 🟢

**File:** `services/api/app/tools/predict_case_duration.py` (currently referenced but empty)

- [ ] **5.1.1** — Define the tool input schema:
  ```python
  class PredictCaseDurationInput(BaseModel):
      case_type: str          # e.g. "land_dispute", "criminal", "family"
      parties_count: int
      complexity: str         # "low" | "medium" | "high"
      court: str              # e.g. "High Court Nairobi"
  ```

- [ ] **5.1.2** — Implement the prediction logic. MVP approach: query Neo4j for historical cases
  matching `case_type` and `court`, compute median duration from the `date` fields. Return
  `{estimated_months: int, confidence: float, similar_cases_count: int}`.

- [ ] **5.1.3** — Wire the tool into the tool node registry in
  `agents/nodes/tool.py`:
  ```python
  TOOLS = {
      "calculator": calculator_tool,
      "predict_case_duration": predict_case_duration_tool,
  }
  ```

- [ ] **5.1.4** — Update the planner system prompt (`nodes/planner.py`) to know about
  `predict_case_duration`: add it to the list of available tools with a description.

---

### 5.2 Add `POST /api/v1/predict/case-duration` route 🟢

**File:** `services/api/app/routes/predict.py` (new file)

- [ ] **5.2.1** — Create the route with a `PredictCaseDurationRequest` Pydantic model.

- [ ] **5.2.2** — Register the router in `main.py`:
  ```python
  app.include_router(predict.router, prefix="/api/v1/predict", tags=["Predict"])
  ```

- [ ] **5.2.3** — Add the endpoint to `API_REFERENCE.md`.

- [ ] **5.2.4** — Add the prediction BPMN flow to `BPMN_WORKFLOWS.md` as Process 8.

---

### 5.3 Add `prediction_history` table 🟢

- [ ] **5.3.1** — Add `PredictionHistory` ORM model to `memory/postgres.py`:
  ```sql
  CREATE TABLE prediction_history (
      id            SERIAL PRIMARY KEY,
      user_id       VARCHAR NOT NULL,
      case_type     VARCHAR(100) NOT NULL,
      court         VARCHAR(200) NOT NULL,
      input_json    JSON NOT NULL,
      predicted_months INTEGER,
      confidence    FLOAT,
      created_at    TIMESTAMP DEFAULT now()
  )
  ```

- [ ] **5.3.2** — Add `save_prediction` and `get_user_predictions` methods.

- [ ] **5.3.3** — Update `DATA_MODEL.md` with the new table.

---

## Phase 6 — Architecture refactoring (tech debt)

---

### 6.1 Split `PostgresMemory` into focused repositories 🟢

**Problem:** `memory/postgres.py` violates SRP — it owns ORM models plus all persistence methods
across 4 unrelated domains (chat, users, verification, ingestion). It also violates ISP — no
route needs all of its methods.

**Tasks:**

- [ ] **6.1.1** — Create `memory/chat_repository.py` — extract `add_message`, `get_history`,
  `get_sessions`, `get_session_messages`.

- [ ] **6.1.2** — Create `memory/user_repository.py` — extract `create_user`, `get_user_by_*`,
  `approve_user`, `activate_user`, `update_user_status`, `seed_admin`, `get_pending_users`,
  `get_users`.

- [ ] **6.1.3** — Create `memory/verification_repository.py` — extract `save_verification`,
  `get_user_verifications`.

- [ ] **6.1.4** — Create `memory/ingestion_repository.py` — extract `create_ingestion_job`,
  `update_ingestion_job`, `get_user_jobs`.

- [ ] **6.1.5** — Keep `memory/postgres.py` for ORM model definitions and engine/session setup
  only. Re-export the four repositories for backward compatibility.

- [ ] **6.1.6** — Update each route to import only the repository it needs via
  `dependencies.py` `Depends()`. No route should import `PostgresMemory` directly.

- [ ] **6.1.7** — Update `memory/models.py` re-exports to point at the new structure.

- [ ] **6.1.8** — Update `ARCHITECTURE.md` component dependency graph to reflect the split.

---

### 6.2 Migrate LangGraph to v0.2+ API 🟢

**Problem:** Both `agents/graph.py` and `agents/legal_research_graph.py` use `set_entry_point()`
which is deprecated in LangGraph 0.2+.

**Tasks:**

- [ ] **6.2.1** — In `agents/graph.py`, replace:
  ```python
  graph.set_entry_point("planner")
  ```
  with:
  ```python
  from langgraph.graph import START
  graph.add_edge(START, "planner")
  ```

- [ ] **6.2.2** — Apply the same change to `agents/legal_research_graph.py`.

- [ ] **6.2.3** — Update `AGENT_DESIGN.md` section 9 (LangGraph Version Notes) to reflect v0.2+
  compatibility.

- [ ] **6.2.4** — Run existing agent node tests to confirm no regression.

---

## Phase 7 — Production readiness

These tasks gate deployment to any shared environment.

---

### 7.1 Replace MailHog with production SMTP 🟢

- [ ] **7.1.1** — Choose SMTP provider (SendGrid, AWS SES, or Postmark). Add API key to `.env`:
  ```env
  SMTP_HOST=smtp.sendgrid.net
  SMTP_PORT=587
  SMTP_USER=apikey
  SMTP_PASSWORD=<sendgrid-api-key>
  ```

- [ ] **7.1.2** — Remove the `mailhog` service from `docker-compose.yml` (or move to a
  `docker-compose.dev.yml` override).

- [ ] **7.1.3** — Test: register a new user, admin approves, verify real activation email is
  received.

---

### 7.2 Rotate all default credentials 🟢

- [ ] **7.2.1** — Change `ADMIN_PASSWORD` from `Admin1234!` in every environment `.env` file.

- [ ] **7.2.2** — Change `POSTGRES_PASSWORD` from `changeme` in `docker-compose.yml` and all
  deployment configs.

- [ ] **7.2.3** — Change `NEO4J_AUTH` from `neo4j/password`.

- [ ] **7.2.4** — Change `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `minioadmin/minioadmin`.

- [ ] **7.2.5** — Generate a strong `JWT_SECRET_KEY`:
  ```bash
  openssl rand -hex 32
  ```

- [ ] **7.2.6** — Run `detect-secrets scan` (`pre-commit run detect-secrets --all-files`) to
  confirm no secrets are committed.

---

### 7.3 Wire Prometheus → Grafana dashboard 🟢

- [ ] **7.3.1** — Add a `grafana` service to `docker-compose.yml` (or a dev override) with a
  datasource pointing at `http://prometheus:9090`.

- [ ] **7.3.2** — Create a Grafana dashboard JSON in `deploy/grafana/sheria_dashboard.json` with
  panels for:
  - `sheria_cache_hits_total{result="hit"}` vs `{result="miss"}` (cache efficiency)
  - `sheria_agent_node_duration_seconds{node="planner|retriever|responder"}` (p50/p95 latency)
  - `sheria_api_request_duration_seconds{endpoint="/api/v1/chat/stream"}` (end-to-end latency)
  - `sheria_retrieval_docs_count{source="combined"}` (retrieval volume)

- [ ] **7.3.3** — Document the Grafana setup in `DEPLOYMENT_GUIDE.md`.

---

### 7.4 Production database hardening 🟢

- [ ] **7.4.1** — Add `?ssl=require` to `DATABASE_URL` in production `.env`:
  ```env
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/sheria_db?ssl=require
  ```

- [ ] **7.4.2** — Enable Qdrant API key authentication. Add `QDRANT_API_KEY` to `config.py` and
  pass it in `clients/qdrant.py` when constructing `QdrantClient`.

- [ ] **7.4.3** — Enable Neo4j role-based access control. Create a read-only Neo4j user for the
  API service (it only reads from Neo4j — ingestion pipeline uses the admin user).

- [ ] **7.4.4** — Set `LOG_LEVEL=WARNING` in staging/production `.env`.

---

## Task dependency graph

```
Phase 1 (pre-merge)
  ├── 1.1 embedding dim ──────────────────────────────────────┐
  ├── 1.2 CORS fix                                            │
  ├── 1.3 PDF size limit                                      │
  └── 1.4 approved_by                                         │
                                                              ▼
Phase 2 (data)                                        Phase 3 (security)
  ├── 2.1 scraper                                      ├── 3.1 rate limiting
  ├── 2.2 ingestion ◄─ depends on 1.1                  ├── 3.2 token revocation
  └── 2.3 smoke test ◄─ depends on 2.2                 └── 3.3 activation TTL
        │
        ▼
Phase 4 (tests) ◄─ depends on 2.2 for integration tests
  ├── 4.1 verify unit tests
  ├── 4.2 verify integration tests
  ├── 4.3 legal research graph tests
  └── 4.4 auth flow integration tests
        │
        ▼
Phase 5 (Sheria Predict) ◄─ depends on 2.2 (needs Neo4j data)
  ├── 5.1 predict tool
  ├── 5.2 predict route
  └── 5.3 prediction_history table
        │
        ▼
Phase 6 (refactor) ◄─ best done after Phase 5 (no new domain growth expected)
  ├── 6.1 split PostgresMemory
  └── 6.2 LangGraph v0.2+ migration
        │
        ▼
Phase 7 (production) ◄─ depends on all above
  ├── 7.1 real SMTP
  ├── 7.2 credential rotation
  ├── 7.3 Grafana dashboard
  └── 7.4 DB hardening
```

---

## Task count summary

| Phase | Tasks | Priority |
|-------|-------|----------|
| 1 — Pre-merge fixes | 14 | 🔴 / 🟡 |
| 2 — Data population | 9 | 🟡 |
| 3 — Security hardening | 15 | 🟡 |
| 4 — Test coverage | 18 | 🟡 |
| 5 — Sheria Predict | 9 | 🟢 |
| 6 — Architecture refactor | 10 | 🟢 |
| 7 — Production readiness | 13 | 🟢 |
| **Total** | **88** | |
