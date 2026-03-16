# Sheria Platform — API Reference

**Base URL:** `http://localhost:8000`
**Authentication:** `Authorization: Bearer <JWT>` (required on all endpoints except `/auth/login`, `/auth/register`, `/auth/activate`, `/health*`)

---

## Authentication Endpoints (`/api/v1/auth`)

### POST `/api/v1/auth/register`

Submit a new staff registration. Status will be `pending` until an admin approves.

**Request:**
```json
{
  "username": "jkimani",
  "email": "j.kimani@judiciary.go.ke",
  "full_name": "Justice Jane Kimani",
  "role": "judge",
  "court_station": "High Court Nairobi",
  "staff_number": "JUD-2024-001"
}
```

**Response 201:**
```json
{
  "message": "Registration submitted. Awaiting admin approval.",
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Validation:**
- `role` must be one of: `judge`, `magistrate`, `registrar`, `clerk`, `admin`
- `username` and `email` must be unique
- Returns `409 Conflict` if username or email already registered

---

### POST `/api/v1/auth/login`

Authenticate and receive a JWT token.

**Request:**
```json
{
  "username": "jkimani",
  "password": "SecureP@ss123"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "jkimani",
    "role": "judge",
    "full_name": "Justice Jane Kimani"
  }
}
```

**Error responses:**
- `401` — Invalid credentials
- `403` — Account not active (pending/suspended)

**JWT Payload:**
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "judge",
  "permissions": [],
  "exp": 1741906800
}
```

**TTL:** 8 hours

---

### POST `/api/v1/auth/activate`

Activate account using the token sent via email after admin approval.

**Request:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "password": "NewSecureP@ss123",
  "confirm_password": "NewSecureP@ss123"
}
```

**Response 200:**
```json
{
  "message": "Account activated successfully. You can now log in."
}
```

**Errors:**
- `400` — Invalid or expired activation token
- `400` — Passwords do not match
- `409` — Account already activated

---

### GET `/api/v1/auth/pending`

**Auth required:** Admin only

List all pending user registrations awaiting approval.

**Response 200:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "jkimani",
    "email": "j.kimani@judiciary.go.ke",
    "full_name": "Justice Jane Kimani",
    "role": "judge",
    "court_station": "High Court Nairobi",
    "staff_number": "JUD-2024-001",
    "created_at": "2026-03-13T08:00:00Z"
  }
]
```

---

### POST `/api/v1/auth/approve/{user_id}`

**Auth required:** Admin only

Approve a pending registration. Triggers async activation email.

**Path parameters:**
- `user_id` — UUID of the pending user

**Response 200:**
```json
{
  "message": "User approved. Activation email sent.",
  "activation_token": "a1b2c3..."
}
```

**Side effects:**
- Sets `user.status = "approved"`
- Generates `activation_token`
- Fires async email to user (non-blocking)

---

### GET `/api/v1/auth/users`

**Auth required:** Admin only

List all users with optional filters.

**Query parameters:**
- `status` — Filter by status (`pending`, `approved`, `active`, `suspended`)
- `role` — Filter by role
- `limit` — Page size (default: 50)
- `offset` — Pagination offset

**Response 200:**
```json
{
  "users": [
    {
      "id": "...",
      "username": "jkimani",
      "email": "j.kimani@judiciary.go.ke",
      "full_name": "Justice Jane Kimani",
      "role": "judge",
      "court_station": "High Court Nairobi",
      "status": "active",
      "created_at": "2026-03-13T08:00:00Z",
      "activated_at": "2026-03-13T09:00:00Z",
      "approved_by": "admin-user-id"
    }
  ],
  "total": 42
}
```

---

### POST `/api/v1/auth/users/{user_id}/status`

**Auth required:** Admin only

Suspend or reactivate a user account.

**Request:**
```json
{
  "action": "suspend"
}
```

**Valid actions:** `suspend`, `reactivate`

**Response 200:**
```json
{
  "message": "User suspended successfully.",
  "user_id": "...",
  "new_status": "suspended"
}
```

---

## Chat Endpoint (`/api/v1/chat`)

### POST `/api/v1/chat/stream`

**Auth required:** Yes

Submit a chat message and receive a streaming response from the AI legal research agent.

**Request:**
```json
{
  "message": "What is the test for adverse possession in Kenya?",
  "session_id": "session-uuid-here"
}
```

**Response:** `Content-Type: application/x-ndjson` (Newline-Delimited JSON stream)

**Stream events:**

Status event (emitted as each agent node starts):
```json
{"event": "status", "node": "planner", "timestamp": "2026-03-13T10:00:00.100Z"}
```

Status event (retriever):
```json
{"event": "status", "node": "retriever", "timestamp": "2026-03-13T10:00:00.300Z"}
```

Cache hit response (immediate, no agent execution):
```json
{"event": "answer", "content": "Based on established Kenyan case law...", "source": "cache"}
```

Final answer event:
```json
{"event": "answer", "content": "The test for adverse possession in Kenya...", "source": "agent"}
```

Error event:
```json
{"event": "error", "message": "Retrieval failed: Qdrant connection timeout"}
```

**Background tasks (after stream completes):**
1. Save user message + AI response to `chat_history`
2. Update semantic cache with new Q&A pair

---

## Upload Endpoint (`/api/v1/upload`)

### POST `/api/v1/upload/generate-presigned-url`

**Auth required:** Yes

Generate a presigned S3/MinIO URL for direct document upload.

**Request:**
```json
{
  "filename": "HC_MISC_APP_123_2025_judgment.pdf",
  "content_type": "application/pdf"
}
```

**Response 200:**
```json
{
  "upload_url": "http://minio:9000/court-records-dev/uploads/user-id/uuid/filename.pdf?X-Amz-Signature=...",
  "file_id": "a1b2c3d4",
  "s3_key": "uploads/550e8400/a1b2c3d4/HC_MISC_APP_123_2025_judgment.pdf",
  "expires_in": 3600
}
```

**Client usage:**
```bash
curl -X PUT "<upload_url>" \
  -H "Content-Type: application/pdf" \
  --data-binary @judgment.pdf
```

**Notes:**
- Presigned URL expires in 3600 seconds (1 hour)
- File is uploaded directly to MinIO/S3, bypassing the API server
- Client is responsible for triggering ingestion after upload completes

---

## Feedback Endpoint (`/api/v1/feedback`)

### POST `/api/v1/feedback/`

**Auth required:** Yes

Submit a rating for an AI assistant response.

**Request:**
```json
{
  "session_id": "session-uuid",
  "message_id": "message-uuid",
  "score": 1,
  "comment": "Accurate citation of Obiero v Republic"
}
```

**Fields:**
- `score`: `1` (thumbs up) or `-1` (thumbs down)
- `comment`: Optional free-text annotation

**Response 201:**
```json
{
  "message": "Feedback recorded.",
  "feedback_id": "..."
}
```

---

## History Endpoints (`/api/v1/history`)

### GET `/api/v1/history/sessions`

**Auth required:** Yes

List all conversation sessions for the authenticated user (newest first).

**Query parameters:**
- `limit` — Page size (default: 20)
- `offset` — Pagination offset

**Response 200:**
```json
{
  "sessions": [
    {
      "session_id": "session-uuid",
      "last_message": "What is the test for adverse possession?",
      "message_count": 6,
      "started_at": "2026-03-13T09:00:00Z",
      "last_activity": "2026-03-13T09:15:00Z"
    }
  ],
  "total": 12
}
```

---

### GET `/api/v1/history/sessions/{session_id}`

**Auth required:** Yes (ownership validated — users can only read their own sessions)

Get all messages in a specific conversation session.

**Path parameters:**
- `session_id` — Session UUID

**Response 200:**
```json
{
  "session_id": "session-uuid",
  "messages": [
    {
      "id": "msg-uuid",
      "role": "user",
      "content": "What is adverse possession?",
      "metadata": {},
      "created_at": "2026-03-13T09:00:00Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Adverse possession in Kenya requires...",
      "metadata": {
        "sources": ["[2023] KESC 45", "[2019] KECA 21"]
      },
      "created_at": "2026-03-13T09:00:05Z"
    }
  ]
}
```

**Errors:**
- `403` — Session belongs to different user
- `404` — Session not found

---

## Health Endpoints

### GET `/health`

General service health — returns aggregated status of all dependencies.

**Response 200:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "postgres": "connected",
    "redis": "connected",
    "qdrant": "connected",
    "neo4j": "connected",
    "ollama": "connected"
  }
}
```

**Response 503** (partial failure):
```json
{
  "status": "degraded",
  "services": {
    "postgres": "connected",
    "redis": "error: Connection refused",
    "qdrant": "connected",
    "neo4j": "connected",
    "ollama": "connected"
  }
}
```

---

### GET `/health/ready`

Kubernetes readiness probe. Returns `200` only if all required services are reachable.

---

### GET `/health/live`

Kubernetes liveness probe. Returns `200` if the process is running.

---

## Metrics Endpoint

### GET `/metrics`

Prometheus metrics exposition (ASGI sub-app mounted at `/metrics`).

**Sample output:**
```
# HELP sheria_api_requests_total Total HTTP requests
# TYPE sheria_api_requests_total counter
sheria_api_requests_total{method="POST",endpoint="/api/v1/chat/stream",status="200"} 1542

# HELP sheria_api_request_duration_seconds HTTP request latency
# TYPE sheria_api_request_duration_seconds histogram
sheria_api_request_duration_seconds_bucket{endpoint="/api/v1/chat/stream",le="1.0"} 120
sheria_api_request_duration_seconds_bucket{endpoint="/api/v1/chat/stream",le="5.0"} 1400
sheria_api_request_duration_seconds_bucket{endpoint="/api/v1/chat/stream",le="+Inf"} 1542

# HELP sheria_cache_hits_total Semantic cache hit/miss counts
# TYPE sheria_cache_hits_total counter
sheria_cache_hits_total{result="hit"} 823
sheria_cache_hits_total{result="miss"} 719

# HELP sheria_agent_node_duration_seconds Time spent in each LangGraph node
# TYPE sheria_agent_node_duration_seconds histogram
sheria_agent_node_duration_seconds_bucket{node="planner",le="0.5"} 700

# HELP sheria_retrieval_docs_count Documents retrieved per source
# TYPE sheria_retrieval_docs_count histogram
sheria_retrieval_docs_count{source="vector"} 3604
sheria_retrieval_docs_count{source="graph"} 2890
sheria_retrieval_docs_count{source="combined"} 5831
```

---

## Verify Endpoints (`/api/v1/verify`)

### POST `/api/v1/verify`

**Auth required:** Yes

Upload a PDF court document and receive an authenticity report. The pipeline extracts metadata via LLM, cross-references the case in Kenya Law Reports (Qdrant), and runs a fraud pattern analysis.

**Request:** `multipart/form-data`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | PDF file | Yes | — | Court document to authenticate |
| `document_type` | string | No | `court_order` | `court_order` \| `judgment` \| `pleading` \| `affidavit` |
| `case_number` | string | No | `""` | Case reference for cross-referencing against Qdrant corpus |

**Response 200:**
```json
{
  "authentic": true,
  "confidence": 0.87,
  "document_type": "court_order",
  "extracted_metadata": {
    "case_number": "HC MISC. APP. 123 OF 2025",
    "court": "High Court Nairobi",
    "date_issued": "2025-03-01",
    "presiding_judge": "Justice Jane Kimani"
  },
  "verification_checks": [
    {"check": "metadata_extraction", "passed": true, "detail": "All metadata fields extracted"},
    {"check": "case_cross_reference", "passed": true, "detail": "Case found in Kenya Law Reports"},
    {"check": "fraud_pattern_analysis", "passed": true, "detail": "No fraud patterns detected"}
  ],
  "risk_flags": [],
  "summary": "Document appears authentic. Case cross-referenced successfully."
}
```

**Errors:**
- `400` — Empty file or invalid/unreadable PDF
- `413` — File exceeds the server's upload limit (`MAX_PDF_UPLOAD_MB`, default **20 MB**)
- `422` — Verification pipeline raised an unrecoverable error

**File size limit:** Controlled by the `MAX_PDF_UPLOAD_MB` environment variable (default `20`). Override in `.env` or `docker-compose.yml`. Files exceeding the limit are rejected immediately after reading, before any LLM processing.

**Side effects:** Saves result to `verification_activity` table via background task.

**Scanned PDF behaviour:** If `pypdf` extracts no text (image-only PDF), the pipeline continues with an empty text string. Checks that require text content will fail gracefully and flag the document as inconclusive rather than crashing.

---

### GET `/api/v1/verify/history`

**Auth required:** Yes

Return the authenticated user's document verification history, newest first (up to 50 records).

**Response 200:**
```json
[
  {
    "id": 1,
    "filename": "court_order_2025.pdf",
    "document_type": "court_order",
    "case_number": "HC MISC. APP. 123 OF 2025",
    "authentic": true,
    "confidence": 0.87,
    "created_at": "2026-03-15T10:00:00Z"
  }
]
```

---

## Legal Research Endpoint (`/api/v1/legal-research`)

### POST `/api/v1/legal-research`

**Auth required:** Yes

Structured judicial research endpoint (streaming). Unlike `/api/v1/chat/stream`, this endpoint:
- **Always retrieves** from Kenya Law Reports — never short-circuits to a direct answer.
- Accepts optional `jurisdiction` and `date_range` filters applied as Qdrant payload filters.
- Returns structured `citations` alongside the IRAC answer text.

**Request:**
```json
{
  "query": "What is the test for adverse possession in Kenya?",
  "jurisdiction": ["Supreme Court", "Court of Appeal"],
  "date_range": {"from": "2010", "to": "2026"},
  "session_id": "optional-session-uuid"
}
```

**Fields:**
- `query` — required, min_length=1
- `jurisdiction` — optional list; valid values: `"Supreme Court"`, `"Court of Appeal"`, `"High Court"`, `"Industrial Court"`. Omit for all courts.
- `date_range.from` / `date_range.to` — year strings (e.g. `"2010"`, `"2026"`)
- `session_id` — optional UUID; auto-generated if omitted

**Response:** `Content-Type: application/x-ndjson`

Status events (emitted as each node starts):
```json
{"event": "status", "step": "retriever", "session_id": "..."}
{"event": "status", "step": "responder", "session_id": "..."}
```

Answer event (final):
```json
{
  "event": "answer",
  "content": "The test for adverse possession in Kenya requires...",
  "citations": [
    {
      "text": "Adverse possession requires actual, open, continuous possession...",
      "source": "supreme_court/waweru_v_republic.pdf",
      "case_number": "[2023] KESC 45",
      "court": "Supreme Court"
    }
  ],
  "session_id": "..."
}
```

Cache hit (immediate, no agent execution):
```json
{"event": "answer", "content": "...", "citations": [], "session_id": "..."}
```

Error event:
```json
{"event": "error", "content": "An internal error occurred during legal research."}
```

**Background tasks (after stream):**
1. Save user query and AI response to `chat_history`
2. Update `semantic_cache` with new Q&A pair

---

## Error Response Format

All error responses use a consistent format:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "trace_id": "uuid-for-support-reference"
}
```

**Common HTTP status codes:**
| Code | Meaning |
|------|---------|
| `400` | Bad request / validation error |
| `401` | Missing or invalid JWT |
| `403` | Insufficient role / ownership violation |
| `404` | Resource not found |
| `409` | Conflict (duplicate username/email) |
| `413` | Payload too large (PDF exceeds `MAX_PDF_UPLOAD_MB`) |
| `422` | Pydantic validation failure |
| `500` | Internal server error |
| `503` | Service dependency unavailable |
