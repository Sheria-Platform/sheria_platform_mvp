# Sheria Platform — Business Process Workflows (BPMN)

This document captures the core business processes as BPMN 2.0 descriptions and Mermaid flow diagrams.

---

## Process 1: User Registration & Activation

**Participants:** Staff Member, System, Admin

### Mermaid Diagram

```mermaid
sequenceDiagram
    actor Staff as Staff Member
    participant API as Sheria API
    participant DB as PostgreSQL
    participant Email as Email Service (MailHog/SMTP)
    actor Admin as System Administrator

    Staff->>API: POST /auth/register\n(username, email, role, court)
    API->>DB: INSERT user (status=pending)
    API-->>Staff: 201 Created "Awaiting admin approval"

    loop Admin Reviews Pending Registrations
        Admin->>API: GET /auth/pending
        API->>DB: SELECT users WHERE status=pending
        API-->>Admin: List of pending users
    end

    Admin->>API: POST /auth/approve/{user_id}
    API->>DB: UPDATE user SET status=approved,\ngenerate activation_token
    API->>Email: [async] Send activation email\nwith token link
    API-->>Admin: 200 "User approved, email sent"

    Email-->>Staff: Email with activation link\n(APP_BASE_URL/activate?token=...)

    Staff->>API: POST /auth/activate\n(token, password, confirm_password)
    API->>DB: Validate token, hash password,\nUPDATE status=active
    API-->>Staff: 200 "Account activated"

    Staff->>API: POST /auth/login\n(username, password)
    API->>DB: Verify bcrypt hash
    API-->>Staff: 200 JWT token (8h TTL)
```

### BPMN 2.0 XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             targetNamespace="http://sheria.judiciary.go.ke/bpmn"
             id="UserRegistrationProcess">

  <collaboration id="Collab_Registration">
    <participant id="Pool_Staff" name="Staff Member" processRef="Proc_Staff"/>
    <participant id="Pool_System" name="Sheria System" processRef="Proc_System"/>
    <participant id="Pool_Admin" name="Administrator" processRef="Proc_Admin"/>
  </collaboration>

  <process id="Proc_System" name="User Registration &amp; Activation" isExecutable="true">

    <!-- Start Event -->
    <startEvent id="Start_Receive_Registration" name="Receive Registration Request">
      <messageEventDefinition messageRef="Msg_Registration"/>
    </startEvent>

    <!-- Task: Validate Input -->
    <serviceTask id="Task_Validate_Input" name="Validate Registration Data">
      <documentation>Validate username uniqueness, email format, role validity</documentation>
    </serviceTask>

    <!-- Gateway: Duplicate Check -->
    <exclusiveGateway id="GW_Duplicate" name="User Already Exists?"/>

    <!-- Task: Reject Duplicate -->
    <serviceTask id="Task_Reject_Duplicate" name="Return 409 Conflict"/>

    <!-- Task: Create Pending User -->
    <serviceTask id="Task_Create_User" name="Create User (status=pending)">
      <documentation>INSERT INTO users with status=pending</documentation>
    </serviceTask>

    <!-- Task: Notify Admin -->
    <serviceTask id="Task_Notify_Admin" name="Return 201 to Staff"/>

    <!-- Intermediate: Wait for Admin Approval -->
    <intermediateCatchEvent id="Wait_Admin_Approval" name="Wait for Admin Approval">
      <messageEventDefinition messageRef="Msg_AdminApproval"/>
    </intermediateCatchEvent>

    <!-- Task: Generate Activation Token -->
    <serviceTask id="Task_Gen_Token" name="Generate Activation Token and Update Status">
      <documentation>status=approved, generate UUID activation_token</documentation>
    </serviceTask>

    <!-- Task: Send Email (Async) -->
    <serviceTask id="Task_Send_Email" name="Send Activation Email (Async)">
      <documentation>aiosmtplib fire-and-forget email with activation link</documentation>
    </serviceTask>

    <!-- Intermediate: Wait for Activation -->
    <intermediateCatchEvent id="Wait_Activation" name="Wait for Staff to Activate">
      <messageEventDefinition messageRef="Msg_Activation"/>
    </intermediateCatchEvent>

    <!-- Task: Validate Token -->
    <serviceTask id="Task_Validate_Token" name="Validate Activation Token"/>

    <!-- Gateway: Token Valid? -->
    <exclusiveGateway id="GW_Token_Valid" name="Token Valid?"/>

    <!-- Task: Reject Invalid Token -->
    <serviceTask id="Task_Reject_Token" name="Return 400 Invalid Token"/>

    <!-- Task: Activate Account -->
    <serviceTask id="Task_Activate" name="Hash Password, Set status=active">
      <documentation>bcrypt hash password, UPDATE users SET status=active, activated_at=now()</documentation>
    </serviceTask>

    <!-- End Events -->
    <endEvent id="End_Success" name="Account Active"/>
    <endEvent id="End_Rejected" name="Registration Rejected"/>
    <endEvent id="End_TokenInvalid" name="Activation Failed"/>

    <!-- Sequence Flows -->
    <sequenceFlow id="sf1" sourceRef="Start_Receive_Registration" targetRef="Task_Validate_Input"/>
    <sequenceFlow id="sf2" sourceRef="Task_Validate_Input" targetRef="GW_Duplicate"/>
    <sequenceFlow id="sf3" sourceRef="GW_Duplicate" targetRef="Task_Reject_Duplicate" name="Yes"/>
    <sequenceFlow id="sf4" sourceRef="GW_Duplicate" targetRef="Task_Create_User" name="No"/>
    <sequenceFlow id="sf5" sourceRef="Task_Reject_Duplicate" targetRef="End_Rejected"/>
    <sequenceFlow id="sf6" sourceRef="Task_Create_User" targetRef="Task_Notify_Admin"/>
    <sequenceFlow id="sf7" sourceRef="Task_Notify_Admin" targetRef="Wait_Admin_Approval"/>
    <sequenceFlow id="sf8" sourceRef="Wait_Admin_Approval" targetRef="Task_Gen_Token"/>
    <sequenceFlow id="sf9" sourceRef="Task_Gen_Token" targetRef="Task_Send_Email"/>
    <sequenceFlow id="sf10" sourceRef="Task_Send_Email" targetRef="Wait_Activation"/>
    <sequenceFlow id="sf11" sourceRef="Wait_Activation" targetRef="Task_Validate_Token"/>
    <sequenceFlow id="sf12" sourceRef="Task_Validate_Token" targetRef="GW_Token_Valid"/>
    <sequenceFlow id="sf13" sourceRef="GW_Token_Valid" targetRef="Task_Reject_Token" name="Invalid"/>
    <sequenceFlow id="sf14" sourceRef="GW_Token_Valid" targetRef="Task_Activate" name="Valid"/>
    <sequenceFlow id="sf15" sourceRef="Task_Reject_Token" targetRef="End_TokenInvalid"/>
    <sequenceFlow id="sf16" sourceRef="Task_Activate" targetRef="End_Success"/>
  </process>

</definitions>
```

---

## Process 2: Legal Research Chat (Agentic RAG)

**Participants:** Judge/Staff, System (API + Agent + Databases)

### Mermaid Flow Diagram

```mermaid
flowchart TD
    A([User sends chat message]) --> B[Validate JWT Token]
    B --> C{Token valid?}
    C -- No --> D([Return 401 Unauthorized])
    C -- Yes --> E[Bind trace context\ntrace_id, session_id, user_id]

    E --> F[Embed query\nnomic-embed-text 768-dim]
    F --> G[Search semantic_cache\nQdrant cosine similarity]
    G --> H{Similarity > 0.95\nAND age < 30 days?}

    H -- Yes: Cache HIT --> I[Stream cached answer\nNDJSON event: source=cache]
    I --> J[Increment CACHE_HITS metric]
    J --> Z([End - Response Sent])

    H -- No: Cache MISS --> K[Load last 6 messages\nfrom PostgreSQL chat_history]
    K --> L[Initialize AgentState\nmessages, query_vector, current_query]

    L --> M[PLANNER NODE\nOllama JSON mode temp=0.0]
    M --> N{Route decision}

    N -- direct_answer --> R[RESPONDER NODE\nOllama qwen3:8b temp=0.3]
    N -- tool_use --> O[TOOL NODE\nExecute tool function]
    O --> R

    N -- retrieve --> P[RETRIEVER NODE\nParallel hybrid search]
    P --> P1[Vector Search\nQdrant top-5 semantic]
    P --> P2[Graph Search\nNeo4j fulltext + 1-hop]
    P1 --> P3[Deduplicate results\nContent-based dedup]
    P2 --> P3
    P3 --> R

    R --> S[Build IRAC prompt\nIssue-Rule-Application-Conclusion]
    S --> T[Stream response tokens\nqwen3:8b max_tokens=1024]
    T --> U[NDJSON stream to client\nevent=answer]

    U --> V[Background Task 1\nSave to chat_history PostgreSQL]
    U --> W[Background Task 2\nUpdate semantic_cache Qdrant]

    V --> Z
    W --> Z
```

### BPMN 2.0 XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://sheria.judiciary.go.ke/bpmn"
             id="LegalResearchChatProcess">

  <process id="Proc_Chat" name="Legal Research Chat" isExecutable="true">

    <startEvent id="Start" name="User Sends Message"/>

    <serviceTask id="Task_ValidateJWT" name="Validate JWT Token"/>
    <exclusiveGateway id="GW_Auth" name="Authenticated?"/>
    <serviceTask id="Task_Return401" name="Return 401 Unauthorized"/>
    <endEvent id="End_Unauthorized"/>

    <serviceTask id="Task_BindContext" name="Bind Trace Context\n(trace_id, session_id, user_id)"/>
    <serviceTask id="Task_EmbedQuery" name="Embed Query\n(nomic-embed-text, 768-dim)"/>
    <serviceTask id="Task_CheckCache" name="Search Semantic Cache\n(Qdrant cosine similarity)"/>

    <exclusiveGateway id="GW_Cache" name="Cache Hit?"/>

    <!-- Cache Hit Path -->
    <serviceTask id="Task_StreamCache" name="Stream Cached Answer\n(source=cache)"/>
    <endEvent id="End_CacheHit" name="Response from Cache"/>

    <!-- Cache Miss Path -->
    <serviceTask id="Task_LoadHistory" name="Load Conversation History\n(Last 6 messages, PostgreSQL)"/>
    <serviceTask id="Task_InitState" name="Initialize AgentState"/>

    <!-- Planner Node -->
    <serviceTask id="Task_Planner" name="PLANNER NODE\nOllama JSON mode (temp=0.0)\nOutputs: action, refined_query"/>
    <exclusiveGateway id="GW_Route" name="Agent Route Decision"/>

    <!-- Retriever Path -->
    <serviceTask id="Task_Retriever" name="RETRIEVER NODE\nParallel: Vector + Graph Search"/>
    <parallelGateway id="PG_Split" name="Parallel Search"/>
    <serviceTask id="Task_VectorSearch" name="Qdrant Vector Search\n(top-5 semantic results)"/>
    <serviceTask id="Task_GraphSearch" name="Neo4j Graph Search\n(fulltext + 1-hop neighbors)"/>
    <parallelGateway id="PG_Join" name="Merge Results"/>
    <serviceTask id="Task_Deduplicate" name="Deduplicate Results\n(content-based)"/>

    <!-- Tool Path -->
    <serviceTask id="Task_Tool" name="TOOL NODE\nExecute tool function"/>

    <!-- Responder Node -->
    <serviceTask id="Task_Responder" name="RESPONDER NODE\nBuild IRAC prompt\nOllama qwen3:8b (temp=0.3)"/>
    <serviceTask id="Task_StreamAnswer" name="Stream Answer to Client\n(NDJSON events)"/>

    <!-- Background Tasks -->
    <parallelGateway id="PG_BG_Split"/>
    <serviceTask id="Task_SaveHistory" name="Save to chat_history\n(PostgreSQL)"/>
    <serviceTask id="Task_UpdateCache" name="Update Semantic Cache\n(Qdrant upsert)"/>
    <parallelGateway id="PG_BG_Join"/>

    <endEvent id="End_AgentResponse" name="Response Sent"/>

    <!-- Sequence Flows: Main Path -->
    <sequenceFlow sourceRef="Start" targetRef="Task_ValidateJWT"/>
    <sequenceFlow sourceRef="Task_ValidateJWT" targetRef="GW_Auth"/>
    <sequenceFlow sourceRef="GW_Auth" targetRef="Task_Return401" name="Invalid"/>
    <sequenceFlow sourceRef="GW_Auth" targetRef="Task_BindContext" name="Valid"/>
    <sequenceFlow sourceRef="Task_Return401" targetRef="End_Unauthorized"/>
    <sequenceFlow sourceRef="Task_BindContext" targetRef="Task_EmbedQuery"/>
    <sequenceFlow sourceRef="Task_EmbedQuery" targetRef="Task_CheckCache"/>
    <sequenceFlow sourceRef="Task_CheckCache" targetRef="GW_Cache"/>

    <!-- Cache paths -->
    <sequenceFlow sourceRef="GW_Cache" targetRef="Task_StreamCache" name="HIT"/>
    <sequenceFlow sourceRef="Task_StreamCache" targetRef="End_CacheHit"/>
    <sequenceFlow sourceRef="GW_Cache" targetRef="Task_LoadHistory" name="MISS"/>

    <!-- Agent path -->
    <sequenceFlow sourceRef="Task_LoadHistory" targetRef="Task_InitState"/>
    <sequenceFlow sourceRef="Task_InitState" targetRef="Task_Planner"/>
    <sequenceFlow sourceRef="Task_Planner" targetRef="GW_Route"/>
    <sequenceFlow sourceRef="GW_Route" targetRef="Task_Retriever" name="retrieve"/>
    <sequenceFlow sourceRef="GW_Route" targetRef="Task_Responder" name="direct_answer"/>
    <sequenceFlow sourceRef="GW_Route" targetRef="Task_Tool" name="tool_use"/>
    <sequenceFlow sourceRef="Task_Tool" targetRef="Task_Responder"/>

    <!-- Retriever parallel -->
    <sequenceFlow sourceRef="Task_Retriever" targetRef="PG_Split"/>
    <sequenceFlow sourceRef="PG_Split" targetRef="Task_VectorSearch"/>
    <sequenceFlow sourceRef="PG_Split" targetRef="Task_GraphSearch"/>
    <sequenceFlow sourceRef="Task_VectorSearch" targetRef="PG_Join"/>
    <sequenceFlow sourceRef="Task_GraphSearch" targetRef="PG_Join"/>
    <sequenceFlow sourceRef="PG_Join" targetRef="Task_Deduplicate"/>
    <sequenceFlow sourceRef="Task_Deduplicate" targetRef="Task_Responder"/>

    <!-- Responder to stream -->
    <sequenceFlow sourceRef="Task_Responder" targetRef="Task_StreamAnswer"/>
    <sequenceFlow sourceRef="Task_StreamAnswer" targetRef="PG_BG_Split"/>
    <sequenceFlow sourceRef="PG_BG_Split" targetRef="Task_SaveHistory"/>
    <sequenceFlow sourceRef="PG_BG_Split" targetRef="Task_UpdateCache"/>
    <sequenceFlow sourceRef="Task_SaveHistory" targetRef="PG_BG_Join"/>
    <sequenceFlow sourceRef="Task_UpdateCache" targetRef="PG_BG_Join"/>
    <sequenceFlow sourceRef="PG_BG_Join" targetRef="End_AgentResponse"/>
  </process>

</definitions>
```

---

## Process 3: Document Upload and Ingestion

### Mermaid Flow Diagram

```mermaid
flowchart TD
    A([User selects document for upload]) --> B[POST /upload/generate-presigned-url\nfilename, content_type]
    B --> C[boto3 generates presigned URL\nKey: uploads/user_id/uuid/filename\nExpiry: 3600s]
    C --> D[Return upload_url, file_id, s3_key]
    D --> E[Client PUTs file binary\ndirectly to MinIO/S3]
    E --> F{Upload successful?}
    F -- No --> G([Client retries or reports error])
    F -- Yes --> H[Client notifies API\nwith file_id and s3_key]
    H --> I[Create ingestion_job record\nstatus=pending]
    I --> J[Ray Data Pipeline triggered]

    J --> K[LOAD: Read binary from MinIO/S3]
    K --> L{Detect file type}
    L -- PDF --> M[PDF Loader\n pdf_loader.py]
    L -- DOCX --> N[DOCX Loader\n docx_loader.py]
    L -- HTML --> O[HTML Loader\n html_loader.py]

    M --> P[CHUNK: 512-token chunks\n50-token overlap\nPreserve legal context]
    N --> P
    O --> P

    P --> Q{Fork}
    Q --> R[Fork A: VECTORIZE]
    Q --> S[Fork B: GRAPH EXTRACT]

    R --> R1[Batch embed via Ollama\nnomic-embed-text]
    R1 --> R2[Index to Qdrant\nkenya_law_reports collection]
    R2 --> R3[Update job stats\nvectors_indexed count]

    S --> S1[Extract entities via LLM\nCase names, judges, principles]
    S1 --> S2[Extract relationships\nCITES, OVERRULES, DISTINGUISHES]
    S2 --> S3[Index to Neo4j\nNodes + Relationships]
    S3 --> S4[Update job stats\ngraph_nodes count]

    R3 --> T[Update ingestion_job\nstatus=completed, duration_s]
    S4 --> T
    T --> U([Document searchable in system])
```

---

## Process 4: Admin User Management

### Mermaid State Diagram

```mermaid
stateDiagram-v2
    [*] --> pending: Staff submits /auth/register

    pending --> approved: Admin calls /auth/approve/{id}\n(generates activation_token,\nsends email)

    pending --> rejected: Admin rejects (future feature)

    approved --> active: Staff calls /auth/activate\n(valid token + password set)

    active --> suspended: Admin calls /users/{id}/status\naction=suspend

    suspended --> active: Admin calls /users/{id}/status\naction=reactivate

    active --> [*]: Account deleted (future feature)
    rejected --> [*]
```

---

## Process 5: Semantic Cache Lifecycle

### Mermaid Flow Diagram

```mermaid
flowchart TD
    A([Incoming query]) --> B[Embed query → 768-dim vector]
    B --> C[Search Qdrant semantic_cache\nwith cosine similarity]
    C --> D{Results found?}

    D -- No --> E([Cache MISS\nProceed to agent])

    D -- Yes --> F{Top result similarity\n> 0.95?}
    F -- No --> E

    F -- Yes --> G{Entry age\n< 30 days?}
    G -- No/Expired --> H[Ignore stale entry]
    H --> E

    G -- Yes: FRESH HIT --> I[Return cached answer\nReuse vector in AgentState]
    I --> J([Cache HIT\nStream cached response])

    E --> K[Agent executes\nProduces answer]
    K --> L[Store Q&A in semantic_cache\nUpsert with created_at timestamp]
    L --> M([Cache populated for future queries])
```

---

## Process 6: Health Check & Startup Sequence

### Mermaid Sequence Diagram

```mermaid
sequenceDiagram
    participant K8s as Kubernetes/Docker
    participant App as FastAPI App
    participant PG as PostgreSQL
    participant Neo4j as Neo4j
    participant Redis as Redis
    participant Qdrant as Qdrant
    participant Ollama as Ollama

    K8s->>App: Container start

    App->>PG: create_async_engine()
    App->>PG: Base.metadata.create_all()
    PG-->>App: Tables ready

    App->>PG: seed_admin() [if no admin exists]
    PG-->>App: Admin seeded (idempotent)

    App->>Neo4j: GraphDatabase.driver()
    Neo4j-->>App: Driver ready

    App->>Redis: aioredis.from_url()
    Redis-->>App: Client ready

    App->>Qdrant: QdrantClient(host, port, grpc_port)
    App->>Qdrant: health_check()
    Qdrant-->>App: OK

    App->>Qdrant: Create semantic_cache collection (if missing)
    Qdrant-->>App: Collection ready

    App->>Ollama: httpx.AsyncClient pool (20 keepalive, 50 max)
    App-->>K8s: Application ready

    loop Every 30s: Liveness probe
        K8s->>App: GET /health/live
        App-->>K8s: 200 OK
    end

    loop Every 10s: Readiness probe
        K8s->>App: GET /health/ready
        App->>PG: ping
        App->>Qdrant: health_check
        App-->>K8s: 200 OK (or 503 if degraded)
    end
```

---

## Process 7: Document Verification (Sheria Verify)

**Participants:** Court Staff/Registrar, Sheria API, Verification Pipeline

### Mermaid Flow Diagram

```mermaid
flowchart TD
    A([User selects PDF document]) --> B[POST /api/v1/verify\nmultipart: file, document_type, case_number]
    B --> C[Validate JWT Token]
    C --> D{JWT valid?}
    D -- No --> E([401 Unauthorized])
    D -- Yes --> F[Read PDF bytes from upload]
    F --> G{PDF bytes empty?}
    G -- Yes --> H([400 Bad Request: empty file])
    G -- No --> I[Extract text via pypdf]
    I --> J{pypdf parse error?}
    J -- Yes --> K([400 Bad Request: invalid PDF])
    J -- No --> L{Text extracted?}
    L -- No text: image-only PDF --> M[Log warning: scanned document\nContinue with empty text]
    L -- Yes --> N[Build tool_input JSON\ndocument_text, document_type, case_number]
    M --> N

    N --> O[verify_document tool\n3-step LLM + Qdrant pipeline]
    O --> O1[Step 1: LLM metadata extraction\nOllama extracts case number, court, judge, date]
    O1 --> O2[Step 2: Qdrant cross-reference\nSearch kenya_law_reports for case citation]
    O2 --> O3[Step 3: Fraud pattern analysis\nLLM evaluates document indicators]
    O3 --> P[Build VerificationReport\nauthentic, confidence, verification_checks, risk_flags, summary]

    P --> Q{Pipeline error?}
    Q -- Yes --> R([422 Unprocessable Entity])
    Q -- No --> S[Return VerificationReport JSON]
    S --> T[Background: save_verification\nto verification_activity table]
    T --> U([Verification complete])
```

### BPMN 2.0 Description

**Process:** `DocumentVerification`
**Participants:** Staff Member (lane), Sheria API (lane), Verification Pipeline (lane)

**Tasks:**
1. `Task_Upload` — Staff POSTs multipart form to `/api/v1/verify`
2. `Task_Auth` — JWT validation via `get_current_user` dependency
3. `Task_ReadPDF` — Read upload bytes into memory
4. `Task_ExtractText` — `pypdf` text extraction (graceful on scanned PDFs)
5. `Task_MetadataExtract` — LLM call: extract structured metadata from document text
6. `Task_CrossReference` — Qdrant search: look up case citation in `kenya_law_reports`
7. `Task_FraudAnalysis` — LLM call: evaluate fraud indicators, assign confidence score
8. `Task_BuildReport` — Assemble `VerificationReport` Pydantic model
9. `Task_PersistActivity` — Background: `save_verification()` → `verification_activity` table

**Gateways:**
- `GW_Auth` — JWT valid? → continue | 401
- `GW_EmptyFile` — bytes > 0? → continue | 400
- `GW_ParseError` — pypdf success? → continue | 400
- `GW_PipelineError` — tool raised exception? → 422 | continue

**End events:**
- `End_Verified` — Report returned to client
- `End_Unauthorized` — 401
- `End_InvalidFile` — 400
- `End_PipelineError` — 422
