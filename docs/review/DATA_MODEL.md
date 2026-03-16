# Sheria Platform — Data Model Reference

---

## 1. PostgreSQL Schema

### 1.1 `users` Table

```sql
CREATE TABLE users (
    id               VARCHAR PRIMARY KEY,     -- UUID string generated at app layer
    username         VARCHAR(50) NOT NULL UNIQUE,
    email            VARCHAR(120) NOT NULL UNIQUE,
    full_name        VARCHAR(200) NOT NULL,
    hashed_password  VARCHAR,                 -- bcrypt hash; NULL until activated
    role             VARCHAR(30) NOT NULL,    -- judge|magistrate|registrar|clerk|admin
    court_station    VARCHAR(200) NOT NULL,   -- required at registration
    staff_number     VARCHAR(50),
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
                     -- pending → approved → active → suspended
    activation_token VARCHAR,                 -- UUID; cleared after use
    approved_by      VARCHAR,                 -- user_id of the admin who approved (audit trail)
    created_at       TIMESTAMP DEFAULT now(),
    activated_at     TIMESTAMP               -- NULL until status=active
);
```

**User lifecycle status values:**

| Status | Meaning | Next valid status |
|--------|---------|------------------|
| `pending` | Registration submitted, awaiting admin review | `approved` |
| `approved` | Admin approved, activation email sent | `active` |
| `active` | Password set, fully operational | `suspended` |
| `suspended` | Admin-suspended; cannot log in | `active` |

**Valid roles:**
- `judge`
- `magistrate`
- `registrar`
- `clerk`
- `admin`

---

### 1.2 `chat_history` Table

```sql
CREATE TABLE chat_history (
    id          SERIAL PRIMARY KEY,       -- Integer autoincrement (not UUID)
    session_id  VARCHAR NOT NULL,
    user_id     VARCHAR NOT NULL,         -- String FK (references users.id by value)
    role        VARCHAR(50) NOT NULL,     -- 'user' | 'assistant' | 'system'
    content     TEXT NOT NULL,
    metadata_   JSON,                     -- sources, node timings, cache_hit flag, etc.
    created_at  TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_chat_history_session ON chat_history(session_id);
CREATE INDEX idx_chat_history_user ON chat_history(user_id);
```

> **Implementation note:** The ORM maps `id` as `Integer` autoincrement, and `user_id` as `String` (not a UUID column type or FK constraint). This means referential integrity with `users.id` is enforced at the application layer, not the database layer.

**`metadata_` JSONB examples:**

For user messages:
```json
{
  "trace_id": "uuid-here"
}
```

For assistant messages:
```json
{
  "sources": ["[2023] KESC 45", "[2019] KECA 21"],
  "cache_hit": false,
  "node_timings": {
    "planner": 0.42,
    "retriever": 1.85,
    "responder": 3.21
  },
  "retrieval_counts": {
    "vector": 5,
    "graph": 3,
    "combined": 7
  }
}
```

---

### 1.3 `feedback` Table

```sql
CREATE TABLE feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  VARCHAR(255) NOT NULL,
    user_id     UUID NOT NULL REFERENCES users(id),
    message_id  VARCHAR(255) NOT NULL,   -- references chat_history.id
    score       SMALLINT NOT NULL,       -- +1 (thumbs up) or -1 (thumbs down)
    comment     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

### 1.4 `ingestion_jobs` Table

```sql
CREATE TABLE ingestion_jobs (
    job_id        VARCHAR PRIMARY KEY,
    user_id       VARCHAR NOT NULL,          -- String FK (references users.id by value)
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
    filename      VARCHAR NOT NULL DEFAULT '',
    s3_key        VARCHAR NOT NULL DEFAULT '',
    started_at    TIMESTAMP,
    completed_at  TIMESTAMP,
    duration_s    FLOAT,
    stats         JSON DEFAULT '{}',          -- vectors_indexed, graph_nodes, errors
    error         TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMP DEFAULT now()
);
```

**`stats` JSONB example:**
```json
{
  "chunks_extracted": 142,
  "vectors_indexed": 142,
  "graph_nodes_created": 23,
  "graph_relationships_created": 41,
  "errors": []
}
```

---

### 1.5 `verification_activity` Table

Audit log of every document verification request. Created in this branch (`sheria-verify-basic-design`).

```sql
CREATE TABLE verification_activity (
    id             SERIAL PRIMARY KEY,
    user_id        VARCHAR NOT NULL,         -- references users.id (app-enforced)
    filename       VARCHAR NOT NULL DEFAULT '',
    document_type  VARCHAR(50) NOT NULL,     -- court_order|judgment|pleading|affidavit
    case_number    VARCHAR NOT NULL DEFAULT '',
    authentic      BOOLEAN NOT NULL,
    confidence     FLOAT NOT NULL,
    report_json    JSON,                     -- full VerificationReport payload
    created_at     TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_verification_activity_user ON verification_activity(user_id);
```

**`report_json` example:**
```json
{
  "authentic": true,
  "confidence": 0.87,
  "document_type": "court_order",
  "extracted_metadata": {"case_number": "HC MISC. APP. 123 OF 2025", "court": "High Court Nairobi"},
  "verification_checks": [
    {"check": "metadata_extraction", "passed": true, "detail": "All fields extracted"},
    {"check": "case_cross_reference", "passed": true, "detail": "Case found in corpus"},
    {"check": "fraud_pattern_analysis", "passed": true, "detail": "No fraud patterns"}
  ],
  "risk_flags": [],
  "summary": "Document appears authentic."
}
```

---

## 2. Qdrant Vector Collections

### 2.1 `kenya_law_reports` Collection

**Purpose:** Primary search corpus — Kenya Law Reports (Supreme Court, Court of Appeal, High Court)

**Configuration:**
```python
VectorParams(
    size=768,              # nomic-embed-text output dimensions
    distance=Distance.COSINE
)
```

**Point structure:**
```python
PointStruct(
    id=str(uuid4()),        # Unique point ID
    vector=[...],           # 768-float embedding
    payload={
        "text": "...",              # Chunk content (512 tokens)
        "source": "path/to/file",   # MinIO object key
        "court": "Supreme Court",
        "date": "2023-03-15",
        "case_number": "[2023] KESC 45",
        "chunk_index": 3,           # Position in original document
        "total_chunks": 28          # Total chunks in document
    }
)
```

**Search call:**
```python
client.search(
    collection_name="kenya_law_reports",
    query_vector=query_embedding,   # 768-float
    limit=5,
    with_payload=True
)
```

---

### 2.2 `semantic_cache` Collection

**Purpose:** Cache of Q&A pairs indexed by query vector for fast semantic retrieval.

**Configuration:**
```python
VectorParams(
    size=768,
    distance=Distance.COSINE
)
```

**Point structure:**
```python
PointStruct(
    id=str(uuid4()),
    vector=query_embedding,
    payload={
        "query": "original user query text",
        "answer": "cached AI response",
        "created_at": "2026-03-13T10:00:00Z"  # ISO 8601 UTC
    }
)
```

**Cache lookup with age filter:**
```python
results = client.search(
    collection_name="semantic_cache",
    query_vector=query_embedding,
    limit=1,
    score_threshold=0.95,   # Only return if similarity > 0.95
    query_filter=Filter(
        must=[
            FieldCondition(
                key="created_at",
                range=DatetimeRange(gte=cutoff_datetime)
            )
        ]
    )
)
```

---

## 3. Neo4j Graph Schema

### 3.1 Node Types

```cypher
// Judicial decision
CREATE (c:Case {
    id: "case-uuid",
    name: "Waweru v Republic",
    citation: "[2023] KESC 45",
    court: "Supreme Court",
    date: date("2023-03-15"),
    text: "full judgment text chunk",
    source: "path/to/document"
})

// Judge or magistrate
CREATE (j:Judge {
    id: "judge-uuid",
    name: "Justice Martha Koome",
    court: "Supreme Court",
    appointment_date: date("2021-05-21")
})

// Legal doctrine, test, or principle
CREATE (p:LegalPrinciple {
    id: "principle-uuid",
    name: "Adverse Possession Test",
    description: "Requirements for adverse possession claim in Kenya",
    domain: "land_law"
})
```

### 3.2 Relationship Types

```cypher
// Citation relationship
CREATE (c1:Case)-[:CITES {paragraph: 45, quote: "as held in..."}]->(c2:Case)

// Precedent reversal
CREATE (newer:Case)-[:OVERRULES {reason: "..."}]->(older:Case)

// Factual distinction
CREATE (c1:Case)-[:DISTINGUISHES {on_facts: "..."}]->(c2:Case)

// Legal principle application
CREATE (c:Case)-[:APPLIES {context: "..."}]->(p:LegalPrinciple)

// Judge presided
CREATE (j:Judge)-[:PRESIDED {role: "presiding_judge"}]->(c:Case)

// Case is at court
CREATE (c:Case)-[:AT_COURT]->(court:Court)
```

### 3.3 Fulltext Index

```cypher
CALL db.index.fulltext.createNodeIndex(
    "legalSearch",
    ["Case", "LegalPrinciple"],
    ["text", "name", "description"]
)
```

**Graph search query used by retriever:**
```cypher
CALL db.index.fulltext.queryNodes('legalSearch', $query)
YIELD node, score
OPTIONAL MATCH (node)-[r]-(neighbor)
RETURN node.text AS text,
       node.citation AS citation,
       type(r) AS relationship,
       neighbor.name AS related_entity,
       score
ORDER BY score DESC
LIMIT 5
```

---

## 4. AgentState TypedDict

```python
class AgentState(TypedDict):
    # Full conversation history — uses operator.add (APPEND only, never overwrite)
    messages: Annotated[list[dict], operator.add]

    # Retrieved context documents from Qdrant + Neo4j
    documents: list[str]

    # Query refined by planner node
    current_query: str

    # Planner's reasoning steps
    plan: list[str]

    # Routing decision from planner
    action: str           # "retrieve" | "direct_answer" | "tool_use"

    # Which tool to invoke (if action="tool_use")
    tool_choice: str

    # Tool input (raw string, parsed by tool node)
    tool_input: str

    # Cached embedding vector (reused across nodes to avoid re-embedding)
    query_vector: list[float]

    # Optional court filter for /api/v1/legal-research (e.g. ["Supreme Court", "Court of Appeal"])
    # Empty list = no filter (return results from all courts)
    jurisdiction_filter: list[str]

    # Structured citations emitted by the retriever node (used by legal-research route only)
    citations: list[dict]
```

> **Usage:** `jurisdiction_filter` and `citations` are used exclusively by `legal_research_graph.py` (the dedicated graph for `/api/v1/legal-research`). The generic chat graph (`graph.py`) leaves these fields empty.

**Message format in `messages` list:**
```python
# User message
{"role": "user", "content": "What is adverse possession?"}

# Assistant message
{"role": "assistant", "content": "Adverse possession in Kenya requires..."}

# System message (in responder prompt)
{"role": "system", "content": "You are a judicial research assistant..."}
```

---

## 5. Pydantic Request/Response Models

### Chat Request
```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    session_id: str = Field(..., description="UUID identifying the conversation")
```

### Auth Models
```python
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    role: Literal["judge", "magistrate", "registrar", "clerk", "admin"]
    court_station: Optional[str] = None
    staff_number: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class ActivateRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    confirm_password: str

class UserStatusRequest(BaseModel):
    action: Literal["suspend", "reactivate"]
```

### Upload Request
```python
class PresignedUrlRequest(BaseModel):
    filename: str = Field(..., description="Original filename including extension")
    content_type: str = Field(..., description="MIME type, e.g. application/pdf")
```

### Feedback Request
```python
class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    score: Literal[1, -1]
    comment: Optional[str] = None
```

---

## 6. JWT Token Structure

```python
# Token payload
{
    "sub": "user-uuid",           # Subject (user ID)
    "id": "user-uuid",            # Duplicate for convenience
    "role": "judge",              # User's role
    "permissions": [],            # Future: fine-grained permissions
    "exp": 1741906800,            # Expiry (Unix timestamp, 8h from issue)
    "iat": 1741878000             # Issued at
}

# Token creation
token = jwt.encode(
    payload,
    settings.JWT_SECRET_KEY,
    algorithm="HS256"
)
```
