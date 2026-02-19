# API Reference — Sheria Platform

Base URL (local development): `http://localhost:8000`  
Base URL (production): `https://api.sheriaplatform.go.ke`

All endpoints that require authentication expect a JWT Bearer token in the `Authorization` header.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Endpoints](#endpoints)
   - [POST /api/v1/chat/stream](#post-apiv1chatstream)
   - [POST /api/v1/feedback/](#post-apiv1feedback)
   - [POST /api/v1/upload/generate-presigned-url](#post-apiv1uploadgenerate-presigned-url)
   - [GET /health/liveness](#get-healthliveness)
   - [GET /health/readiness](#get-healthreadiness)
3. [Response Formats](#response-formats)
4. [Error Codes](#error-codes)
5. [Rate Limiting](#rate-limiting)

---

## Authentication

The API uses **JWT (JSON Web Token)** Bearer authentication. Tokens are signed with HS256 and expire after one hour by default.

### Token Format

```
Authorization: Bearer <jwt-token>
```

### Obtaining a Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "judge.kamau",
    "password": "secure-password",
    "role": "judge"
  }'
```

Response:

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJqdWRnZS5rYW1hdSIsInJvbGUiOiJqdWRnZSIsImV4cCI6MTcwOTk5OTk5OX0.signature",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
        "id": "usr_abc123",
        "name": "Hon. Justice Kamau",
        "role": "judge",
        "court": "High Court Nairobi"
    }
}
```

### User Roles

| Role | Access Level |
|---|---|
| `judge` | Legal research, document verification, case prediction, feedback |
| `magistrate` | Legal research, document verification, feedback |
| `registrar` | Document verification, upload |
| `clerk` | Upload, read-only research |
| `chief_justice` | All endpoints including `/api/v1/analytics/workload` |

---

## Endpoints

### POST /api/v1/chat/stream

Executes a legal research query through the LangGraph agentic pipeline and returns a **Server-Sent Events (SSE)** streaming response. The response streams node-by-node as the agent progresses through Planner → Retriever → Analyzer → Responder.

**Authentication**: Required  
**Roles**: `judge`, `magistrate`, `clerk`

#### Request Body

```json
{
    "query": "string",
    "session_id": "string",
    "user_role": "string",
    "jurisdiction": ["string"],
    "date_range": {
        "from": "YYYY-MM-DD",
        "to": "YYYY-MM-DD"
    },
    "top_k": 5
}
```

| Field | Type | Required | Description |
|---|---|:---:|---|
| `query` | string | Yes | The legal research question in plain English |
| `session_id` | string | Yes | Client-generated session UUID for conversation continuity |
| `user_role` | string | Yes | Must match the token role (`judge`, `magistrate`, `clerk`) |
| `jurisdiction` | string[] | No | Filter by court: `"Supreme Court"`, `"Court of Appeal"`, `"High Court"` |
| `date_range.from` | string | No | ISO 8601 date; restrict results from this date |
| `date_range.to` | string | No | ISO 8601 date; restrict results up to this date |
| `top_k` | integer | No | Number of case law chunks to retrieve (default: 5, max: 20) |

#### SSE Event Types

The response is an NDJSON stream where each line is a JSON object with an `event` field.

| Event Type | When Emitted | Payload |
|---|---|---|
| `status` | Each pipeline stage start | `{"stage": "planner", "message": "..."}` |
| `answer` | Each LLM output token | `{"token": "word"}` |
| `citations` | After answer completes | `{"cases": [...], "statutes": [...]}` |
| `error` | On unrecoverable error | `{"code": "...", "message": "..."}` |
| `done` | Stream complete | `{"session_id": "...", "confidence": 0.0-1.0}` |

#### Curl Example

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "What is the test for adverse possession under Kenyan land law?",
    "session_id": "sess-550e8400-e29b-41d4-a716",
    "user_role": "judge",
    "jurisdiction": ["Supreme Court", "Court of Appeal"],
    "date_range": {"from": "2010-01-01", "to": "2026-02-18"},
    "top_k": 8
  }'
```

#### Example Stream Response

```
{"event":"status","data":{"stage":"planner","message":"Refining legal query for land law domain"}}
{"event":"status","data":{"stage":"retriever","message":"Searching Kenya Law Reports vector index"}}
{"event":"status","data":{"stage":"retriever","message":"Querying citation graph for binding precedents"}}
{"event":"status","data":{"stage":"analyzer","message":"Validating precedent hierarchy"}}
{"event":"answer","data":{"token":"Under"}}
{"event":"answer","data":{"token":" Kenyan"}}
{"event":"answer","data":{"token":" land"}}
{"event":"answer","data":{"token":" law,"}}
{"event":"answer","data":{"token":" the"}}
{"event":"answer","data":{"token":" test"}}
{"event":"answer","data":{"token":" for"}}
{"event":"answer","data":{"token":" adverse"}}
{"event":"answer","data":{"token":" possession"}}
{"event":"answer","data":{"token":" requires..."}}
{"event":"citations","data":{"cases":[{"citation":"[2019] KECA 45","title":"Muthoni v. Kamau","court":"Court of Appeal","relevance":0.94},{"citation":"[2021] KEHC 1203","title":"Njuguna v. Land Board","court":"High Court","relevance":0.88}],"statutes":["Land Registration Act, Cap 300, s. 28"]}}
{"event":"done","data":{"session_id":"sess-550e8400-e29b-41d4-a716","confidence":0.92,"tokens_used":512}}
```

---

### POST /api/v1/feedback/

Records judge or user feedback on an AI-generated response. Feedback is used to fine-tune future model responses and track judicial satisfaction.

**Authentication**: Required  
**Roles**: `judge`, `magistrate`, `clerk`

#### Request Body

```json
{
    "session_id": "string",
    "response_id": "string",
    "rating": 1,
    "comment": "string",
    "cited_cases_accurate": true,
    "was_helpful": true
}
```

| Field | Type | Required | Description |
|---|---|:---:|---|
| `session_id` | string | Yes | Session ID from the original chat stream |
| `response_id` | string | Yes | Unique ID of the response being rated |
| `rating` | integer | Yes | Score from 1 (poor) to 5 (excellent) |
| `comment` | string | No | Free-text feedback from the judge |
| `cited_cases_accurate` | boolean | No | Were the cited cases correctly identified? |
| `was_helpful` | boolean | No | Did the response help with the legal task? |

#### Response Body

```json
{
    "feedback_id": "fb_7f3a9c2d",
    "status": "recorded",
    "message": "Thank you. Your feedback improves future responses."
}
```

#### Curl Example

```bash
curl -X POST http://localhost:8000/api/v1/feedback/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "session_id": "sess-550e8400-e29b-41d4-a716",
    "response_id": "resp-abc123",
    "rating": 4,
    "comment": "Correctly identified the Muthoni v. Kamau case but missed the statutory reference.",
    "cited_cases_accurate": true,
    "was_helpful": true
  }'
```

---

### POST /api/v1/upload/generate-presigned-url

Generates a time-limited presigned URL for uploading a court document (PDF, DOCX) directly to MinIO/S3 from the client. After the upload completes, the document is automatically queued for ingestion into the Qdrant and Neo4j indexes.

**Authentication**: Required  
**Roles**: `judge`, `registrar`, `clerk`

#### Request Body

```json
{
    "filename": "string",
    "content_type": "string",
    "document_type": "string",
    "case_number": "string",
    "court": "string",
    "metadata": {}
}
```

| Field | Type | Required | Description |
|---|---|:---:|---|
| `filename` | string | Yes | Original filename including extension (e.g., `judgment_2026.pdf`) |
| `content_type` | string | Yes | MIME type: `application/pdf` or `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `document_type` | string | Yes | One of: `judgment`, `ruling`, `pleading`, `exhibit`, `court_order` |
| `case_number` | string | Yes | Official case number (e.g., `HC MISC. APP. 123 OF 2025`) |
| `court` | string | Yes | Court identifier (e.g., `High Court Nairobi`) |
| `metadata` | object | No | Additional key-value pairs (judge, parties, legal subject) |

#### Response Body

```json
{
    "upload_url": "http://localhost:9000/kenya-law-reports/uploads/judgment_2026_a1b2c3.pdf?X-Amz-Algorithm=...",
    "document_id": "doc_a1b2c3d4",
    "expires_in": 900,
    "fields": {
        "key": "uploads/judgment_2026_a1b2c3.pdf",
        "Content-Type": "application/pdf"
    },
    "ingestion_job_id": "job_xyz789"
}
```

#### Complete Upload Flow

**Step 1**: Request presigned URL

```bash
curl -X POST http://localhost:8000/api/v1/upload/generate-presigned-url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "filename": "SC_Petition_001_2025.pdf",
    "content_type": "application/pdf",
    "document_type": "judgment",
    "case_number": "SC Petition No. 001 of 2025",
    "court": "Supreme Court",
    "metadata": {
      "judges": ["CJ Martha Koome", "DCJ Philomena Mwilu"],
      "legal_subject": "constitutional_law"
    }
  }'
```

**Step 2**: Upload file directly to MinIO/S3 using the returned URL

```bash
curl -X PUT "$UPLOAD_URL" \
  -H "Content-Type: application/pdf" \
  --data-binary @SC_Petition_001_2025.pdf
```

The document will appear in the ingestion queue within 60 seconds and be fully indexed within 5-10 minutes depending on file size.

---

### GET /health/liveness

Kubernetes liveness probe. Returns 200 if the API process is running.

**Authentication**: None required

#### Response

```json
{
    "status": "alive",
    "timestamp": "2026-02-18T09:30:00.000Z",
    "version": "1.0.0"
}
```

---

### GET /health/readiness

Kubernetes readiness probe. Checks connectivity to all required downstream dependencies. Returns 200 only when all dependencies are reachable.

**Authentication**: None required

#### Response (all healthy)

```json
{
    "status": "ready",
    "dependencies": {
        "postgres": {
            "status": "ok",
            "latency_ms": 2
        },
        "redis": {
            "status": "ok",
            "latency_ms": 1
        },
        "qdrant": {
            "status": "ok",
            "latency_ms": 4,
            "collection": "kenya_law_reports",
            "vectors_count": 142857
        },
        "neo4j": {
            "status": "ok",
            "latency_ms": 8
        },
        "ollama": {
            "status": "ok",
            "latency_ms": 45,
            "models_loaded": ["llama3.3", "nomic-embed-text"]
        },
        "minio": {
            "status": "ok",
            "latency_ms": 3
        }
    },
    "timestamp": "2026-02-18T09:30:00.000Z"
}
```

#### Response (dependency unhealthy — HTTP 503)

```json
{
    "status": "not_ready",
    "dependencies": {
        "postgres": {"status": "ok", "latency_ms": 2},
        "redis": {"status": "ok", "latency_ms": 1},
        "qdrant": {"status": "error", "error": "Connection refused"},
        "neo4j": {"status": "ok", "latency_ms": 8},
        "ollama": {"status": "ok", "latency_ms": 45},
        "minio": {"status": "ok", "latency_ms": 3}
    },
    "timestamp": "2026-02-18T09:30:00.000Z"
}
```

---

## Response Formats

### Streaming (NDJSON)

The `/api/v1/chat/stream` endpoint returns **Newline-Delimited JSON (NDJSON)**. Each line is a complete, independently parseable JSON object. Clients must read the response line-by-line and parse each line individually.

```
Content-Type: application/x-ndjson
Transfer-Encoding: chunked
```

**Parsing example (Python)**:

```python
import httpx

with httpx.stream("POST", "http://localhost:8000/api/v1/chat/stream",
                  json=payload, headers=headers) as response:
    for line in response.iter_lines():
        if line.strip():
            event = json.loads(line)
            if event["event"] == "answer":
                print(event["data"]["token"], end="", flush=True)
            elif event["event"] == "done":
                print(f"\n\nCitations: {event['data']}")
```

**Parsing example (JavaScript)**:

```javascript
const response = await fetch('/api/v1/chat/stream', { method: 'POST', ... });
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
        if (line.trim()) {
            const event = JSON.parse(line);
            if (event.event === 'answer') process.stdout.write(event.data.token);
        }
    }
}
```

---

## Error Codes

| HTTP Status | Code | Description | Resolution |
|---|---|---|---|
| `400` | `INVALID_REQUEST` | Request body failed validation | Check the request schema and required fields |
| `401` | `UNAUTHORIZED` | Missing or invalid JWT token | Obtain a fresh token via `/api/v1/auth/login` |
| `403` | `FORBIDDEN` | User role lacks permission for this endpoint | Use a user account with the required role |
| `404` | `NOT_FOUND` | Resource (session, document) does not exist | Verify the ID and that the resource was created |
| `413` | `FILE_TOO_LARGE` | Uploaded document exceeds 50 MB limit | Split the document or compress before upload |
| `422` | `UNPROCESSABLE_ENTITY` | Semantic validation failed (e.g., invalid case number format) | Check field-level validation errors in the response body |
| `429` | `RATE_LIMITED` | Too many requests from this user | Wait for the retry-after period indicated in the header |
| `500` | `INTERNAL_ERROR` | Unexpected server error | Check server logs; contact support if persistent |
| `503` | `SERVICE_UNAVAILABLE` | A required dependency (Ollama, Qdrant) is not reachable | Check `/health/readiness` to identify the failing service |

Error response body format:

```json
{
    "error": {
        "code": "UNAUTHORIZED",
        "message": "JWT token has expired. Please obtain a new token.",
        "request_id": "req_abc123xyz",
        "timestamp": "2026-02-18T09:30:00.000Z"
    }
}
```

---

## Rate Limiting

Rate limits are applied per user (JWT subject) using a sliding window algorithm backed by Redis.

| Endpoint | Limit | Window |
|---|---|---|
| `POST /api/v1/chat/stream` | 30 requests | 1 minute |
| `POST /api/v1/feedback/` | 60 requests | 1 minute |
| `POST /api/v1/upload/generate-presigned-url` | 20 requests | 1 minute |
| All other endpoints | 120 requests | 1 minute |

When a limit is exceeded, the API responds with HTTP `429` and the following headers:

```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1740045600
Retry-After: 45
```

Contact the judicial system administrator to request increased limits for bulk ingestion or data migration operations.
