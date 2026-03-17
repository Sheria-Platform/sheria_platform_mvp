# Sheria Platform — Security Design

---

## 1. Authentication Model

### JWT Authentication (HS256)

All protected endpoints require a valid JWT in the `Authorization: Bearer <token>` header.

```
Token lifecycle:
  1. User POST /auth/login (username + bcrypt password verification)
  2. Server issues JWT signed with JWT_SECRET_KEY (HS256)
  3. Token TTL: 8 hours
  4. No refresh token mechanism (re-login required after expiry)
```

**Token payload:**
```json
{
  "sub": "user-uuid",
  "id": "user-uuid",
  "role": "judge",
  "permissions": [],
  "exp": 1741906800
}
```

**Validation dependency (`auth/jwt.py`):**
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except JWTError:
        raise HTTPException(401, "Invalid token")
```

**Reviewer notes:**
- `JWT_SECRET_KEY` must be a strong random value (minimum 32 bytes)
- No token revocation mechanism — suspended users' existing tokens remain valid until expiry
- Consider adding a token blacklist (Redis) when suspending users for immediate effect

---

## 2. Authorization Model

### Role-Based Access Control

| Endpoint | Required Role | Implementation |
|----------|-------------|---------------|
| `GET /auth/pending` | `admin` | `require_admin` dependency |
| `POST /auth/approve/{id}` | `admin` | `require_admin` dependency |
| `GET /auth/users` | `admin` | `require_admin` dependency |
| `POST /auth/users/{id}/status` | `admin` | `require_admin` dependency |
| `POST /chat/stream` | Any authenticated | `get_current_user` |
| `POST /upload/...` | Any authenticated | `get_current_user` |
| `POST /feedback/` | Any authenticated | `get_current_user` |
| `GET /history/sessions` | Any authenticated | `get_current_user` (user-scoped) |
| `GET /history/sessions/{id}` | Any authenticated | `get_current_user` + ownership check |
| `GET /auth/me` | Any authenticated | `get_current_user` (own record only) |
| `PATCH /auth/me` | Any authenticated | `get_current_user` (own record only) |
| `POST /auth/me/avatar` | Any authenticated | `get_current_user` (own record only) |

```python
def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user
```

### Session Ownership Enforcement

History endpoints validate that the requesting user owns the session:

```python
async def get_session_messages(session_id: str, user_id: str):
    # Validates user_id matches session owner before returning messages
    session = await db.get_session(session_id)
    if session.user_id != user_id:
        raise HTTPException(403, "Access denied")
```

---

## 3. Password Security

- **Hashing:** bcrypt via `passlib` with default work factor (12 rounds)
- **Storage:** Only `hashed_password` stored in database; plaintext never persisted
- **Activation flow:** Password is NOT set at registration; set only during activation
- `hashed_password` is `NULL` until `status=active`

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash
hashed = pwd_context.hash(plain_password)

# Verify
is_valid = pwd_context.verify(plain_password, hashed)
```

---

## 4. User Registration Security

The supervised registration workflow prevents unauthorized access:

```
1. Staff submits registration → status=pending (CANNOT log in yet)
2. Admin reviews and explicitly approves (out-of-band verification expected)
3. Activation email sent with time-limited token
4. Staff sets password via token → status=active (CAN log in)
```

**Activation token:** UUID generated at approval time. Single-use — cleared after activation.

**Reviewer concerns:**
- Token has no explicit expiry check in current implementation — verify if TTL is enforced
- SMTP credentials are optional (`SMTP_HOST=""` disables email) — in dev, MailHog captures emails
- If email fails silently, admin must manually share token with user

---

## 5. S3 Presigned URL Security

```
Presigned URL properties:
- Signed by AWS/MinIO credentials (never exposed to client)
- Scoped to specific S3 key (uploads/{user_id}/{uuid}/{filename})
- Expiry: 3600 seconds (1 hour)
- Method: PUT only (client can only upload, not read other keys)
- Content-type enforced in signature
```

**Key path structure prevents path traversal:**
```
uploads/{user_id}/{file_uuid}/{sanitized_filename}
```

**Reviewer concern:** Filename sanitization — verify that `filename` from request is sanitized before use in S3 key to prevent directory traversal.

---

## 6. Input Validation

All API inputs are validated via Pydantic models:

| Input | Validation |
|-------|-----------|
| JWT token | `jwt.decode()` signature + expiry verification |
| Registration role | `Literal["judge","magistrate","registrar","clerk","admin"]` |
| Feedback score | `Literal[1, -1]` |
| User status action | `Literal["suspend", "reactivate"]` |
| Chat message | `min_length=1, max_length=4096` |
| Password | `min_length=8` |
| Email | `EmailStr` (Pydantic email validator) |

**LLM prompt injection:** User input is inserted into LLM prompts. No explicit prompt injection defense beyond the IRAC system prompt constraints. Consider adding input sanitization for production.

---

## 7. Secrets Management

| Secret | How Provided | Risk if Leaked |
|--------|-------------|---------------|
| `JWT_SECRET_KEY` | Environment variable | All tokens can be forged |
| `DATABASE_URL` | Environment variable | Full DB access |
| `NEO4J_PASSWORD` | Environment variable | Full graph access |
| `MINIO_ROOT_PASSWORD` | Environment variable | Full object storage access |
| `SMTP_PASSWORD` | Environment variable | Email account compromise |
| `ADMIN_PASSWORD` | Environment variable | Admin account takeover |

**Reviewer verification:**
- No secrets in source code (verify `.env.example` has no real values)
- `.env` excluded from git via `.gitignore`
- Docker Compose reads from `.env` file — not in image

---

## 8. CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.100.104:3000",  # LAN dev machine
        "http://0.0.0.0:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Reviewer concern:** All four origins are hard-coded, including a specific LAN IP (`192.168.100.104`). Production requires a configurable `ALLOWED_ORIGINS` environment variable. The LAN IP will break in any other developer's environment and must not reach staging/production.

---

## 9. Audit Logging

Every HTTP request is logged with:
- `trace_id` — Unique per request (UUID)
- `user_id` — From JWT
- `session_id` — Conversation identifier
- `method`, `path`, `status_code`
- `duration_ms`

```json
{
  "timestamp": "2026-03-13T10:00:00Z",
  "level": "INFO",
  "trace_id": "a1b2c3d4",
  "user_id": "user-uuid",
  "session_id": "session-uuid",
  "method": "POST",
  "path": "/api/v1/chat/stream",
  "status_code": 200,
  "duration_ms": 4523
}
```

---

## 10. Admin Approval Audit Trail

The `users` table includes an `approved_by` column (`VARCHAR`, nullable) that stores the `user_id` of the admin who approved a registration. This provides a lightweight audit trail for accountability.

**Reviewer note:** Confirm that `approved_by` is populated in the approval handler (`POST /auth/approve/{user_id}`) and that it is included in the admin user-list response for auditability.

---

## 11. Verify Endpoint Security

The `POST /api/v1/verify` endpoint accepts a multipart PDF upload.

**Controls in place:**
- JWT authentication required
- File content validated: empty file → 400, invalid PDF → 400
- No file stored on disk — bytes read into memory, text extracted via `pypdf`, bytes discarded

**Reviewer concerns:**
- **Filename sanitization:** The `file.filename` from the multipart upload is passed directly to `memory.save_verification()`. Confirm this is stored as metadata only (not used in any file path or shell command) to prevent path traversal
- **File size limit:** No explicit size cap on uploaded PDFs — a malformed multi-GB PDF could cause OOM. Consider adding `Content-Length` validation or FastAPI's `max_upload_size`
- **Image PDFs:** Scanned documents yield empty text; the pipeline continues without error. Ensure responses clearly indicate "no text extracted" to prevent false confidence in verification results

---

## 12. Avatar Upload Security (`POST /api/v1/auth/me/avatar`)

**Controls in place:**
- JWT authentication required.
- Content-type validated against allowlist `{image/jpeg, image/png, image/webp}` → `415` on violation.
- File size validated ≤ `MAX_AVATAR_UPLOAD_MB` (default 5 MB, env-configurable) → `413` on violation.
- Object stored under deterministic key `avatars/{user_id}.{ext}` — no user-controlled path component.
- File read entirely into memory, then uploaded to MinIO/S3 via boto3 in a thread executor; never written to disk.
- Service availability guarded: returns `503` if `S3_BUCKET_NAME` is not configured (no silent failure).
- Presigned GET URL (TTL = 3600 s) generated and returned — bucket does not need to be public.

**Reviewer concerns:**
- **MIME-type spoofing:** Content-type is taken from the `UploadFile.content_type` header provided by the browser. A malicious client could send `image/jpeg` with a non-image payload. Consider adding server-side magic-byte validation (e.g., `python-magic`) for production hardening.
- **Storage growth:** Uploading a new avatar overwrites the existing S3 key (same deterministic key per user), so there is no unbounded per-user accumulation. Old objects are replaced, not accumulated.
- **Presigned URL leakage:** The presigned URL is returned in the API response and embedded in the frontend. It is time-limited (1 hour). No sensitive data is in the URL beyond the object key.

---

## 13. Profile Update Security (`PATCH /api/v1/auth/me`)

**Controls in place:**
- Scoped to the authenticated user's own record — no `user_id` parameter in the request body or path; user ID taken exclusively from the validated JWT.
- Non-empty validation: any provided field must be a non-empty, non-whitespace string (empty strings rejected with `422`).
- Only four fields are writable via this endpoint: `full_name`, `staff_number`, `bio`, `phone`. Role, court_station, email, status are not writable by the user.

**Reviewer concern:** `bio` and `phone` are free-text with no length cap in the Pydantic model. Consider adding `max_length` constraints (e.g., `bio: str | None = Field(None, max_length=500)`) before production.

---

## 14. Security Checklist for PR Review

- [ ] **JWT_SECRET_KEY** is not hardcoded or in `.env.example`
- [ ] **Admin seed password** (`ADMIN_PASSWORD`) is changed from default `Admin1234!` in production
- [ ] **Token revocation** on user suspension (current: tokens valid until TTL expiry)
- [ ] **Activation token TTL** — verify tokens expire after a reasonable period
- [ ] **Filename sanitization** in presigned URL key construction AND in verify endpoint metadata storage
- [ ] **CORS origins** configurable for production (remove hardcoded LAN IP `192.168.100.104`)
- [ ] **SQL injection** — all queries use parameterized ORM calls (no raw SQL with interpolation)
- [ ] **Password policy** — minimum 8 characters; consider adding complexity requirements
- [ ] **Rate limiting** — no rate limiting on login endpoint (brute force risk)
- [ ] **Prompt injection** — user input passed to LLM without sanitization (chat and verify pipelines)
- [ ] **Error messages** — HTTP errors should not leak internal details (stack traces)
- [ ] **Neo4j Cypher injection** — verify `$query` parameter is safely parameterized
- [ ] **`approved_by` field** — verify populated on approval and included in admin audit logs
- [ ] **PDF upload size limit** — no `max_upload_size` cap on verify endpoint; add before production
- [ ] **Embedding dimension** — `_EMBEDDING_DIM = 768` in `main.py`; confirm this matches actual `nomic-embed-text` output to avoid silent vector shape errors in Qdrant
- [ ] **Avatar MIME-type spoofing** — content-type header is browser-supplied; consider server-side magic-byte validation for production
- [ ] **Profile bio/phone length** — no `max_length` constraint on `bio`/`phone` in `ProfileUpdateRequest`; add limits before production
- [ ] **Profile endpoint ownership** — `PATCH /auth/me` and `POST /auth/me/avatar` derive user ID from JWT only; confirm no user_id override is possible through request body
