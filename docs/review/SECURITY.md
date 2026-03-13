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
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Reviewer concern:** Hard-coded `localhost:3000`. Production requires configurable `ALLOWED_ORIGINS` from environment variable.

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

## 10. Security Checklist for PR Review

- [ ] **JWT_SECRET_KEY** is not hardcoded or in `.env.example`
- [ ] **Admin seed password** (`ADMIN_PASSWORD`) is changed from default `Admin1234!` in production
- [ ] **Token revocation** on user suspension (current: tokens valid until TTL expiry)
- [ ] **Activation token TTL** — verify tokens expire after a reasonable period
- [ ] **Filename sanitization** in presigned URL key construction
- [ ] **CORS origins** configurable for production deployment
- [ ] **SQL injection** — all queries use parameterized ORM calls (no raw SQL with interpolation)
- [ ] **Password policy** — minimum 8 characters; consider adding complexity requirements
- [ ] **Rate limiting** — no rate limiting on login endpoint (brute force risk)
- [ ] **Prompt injection** — user input passed to LLM without sanitization
- [ ] **Error messages** — HTTP errors should not leak internal details (stack traces)
- [ ] **Neo4j Cypher injection** — verify `$query` parameter is safely parameterized
