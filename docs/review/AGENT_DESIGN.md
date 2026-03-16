# Sheria Platform — LangGraph Agent Design

---

## 1. Agent Overview

The Sheria legal research agent is a **LangGraph state machine** that orchestrates multi-step reasoning over Kenya Law Reports. It receives a user query, routes it through appropriate processing nodes, retrieves relevant case law, and synthesizes a cited response.

**Design principles:**
- Typed state propagation (no mutable side-effects between nodes)
- Deterministic routing via structured LLM output (JSON mode)
- Parallel retrieval to minimize latency
- IRAC (Issue-Rule-Application-Conclusion) structured prompting
- Fallback safety — planner errors default to `retrieve` action

---

## 2. Agent State Machine

### State Definition (`agents/state.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list[dict], operator.add]  # Append-only message history
    documents: list[str]                            # Retrieved context docs
    current_query: str                              # Refined query from planner
    plan: list[str]                                 # Reasoning steps
    action: str                                     # Route: retrieve|direct_answer|tool_use
    tool_choice: str                                # Tool name (if tool_use)
    tool_input: str                                 # Tool input string
    query_vector: list[float]                       # Cached 768-dim embedding
    jurisdiction_filter: list[str]                  # Court filter for legal-research route
    citations: list[dict]                           # Structured citations from retriever
```

**Field usage by graph:**
| Field | Chat graph (`graph.py`) | Legal research graph (`legal_research_graph.py`) |
|-------|------------------------|--------------------------------------------------|
| `jurisdiction_filter` | Always empty `[]` | Populated from request (e.g. `["Supreme Court"]`) |
| `citations` | Not used | Populated by retriever; included in final answer event |

**Critical note on `messages`:** The `Annotated[list, operator.add]` annotation means LangGraph uses `operator.add` to merge state updates — messages are appended, never overwritten. This is the correct pattern for conversation history.

---

## 3. Graph Topology

```
                    Entry
                      │
                      ▼
              ┌───────────────┐
              │   PLANNER     │
              │  (JSON mode)  │
              └───────┬───────┘
                      │
              ┌───────▼────────────────────────┐
              │    Conditional Router           │
              │  action = state["action"]       │
              └───┬───────────┬────────────────┘
                  │           │                 │
            "retrieve"  "direct_answer"    "tool_use"
                  │           │                 │
         ┌────────▼────┐      │         ┌───────▼──────┐
         │  RETRIEVER  │      │         │     TOOL     │
         │  (parallel) │      │         │   (execute)  │
         └────────┬────┘      │         └───────┬──────┘
                  │           │                 │
                  └─────┬─────┘─────────────────┘
                        │
                ┌───────▼───────┐
                │   RESPONDER   │
                │  (streaming)  │
                └───────┬───────┘
                        │
                       END
```

### Graph Construction (`agents/graph.py`)

```python
graph = StateGraph(AgentState)

# Add nodes
graph.add_node("planner", planner_node)
graph.add_node("retriever", retrieve_node)
graph.add_node("tool", tool_node)
graph.add_node("responder", generate_node)

# Entry point
graph.set_entry_point("planner")

# Conditional routing from planner
graph.add_conditional_edges(
    "planner",
    route_after_planner,
    {
        "retrieve": "retriever",
        "direct_answer": "responder",
        "tool_use": "tool",
    }
)

# Both retriever and tool flow to responder
graph.add_edge("retriever", "responder")
graph.add_edge("tool", "responder")

# Responder terminates
graph.add_edge("responder", END)

app = graph.compile()
```

**Router function:**
```python
def route_after_planner(state: AgentState) -> str:
    action = state.get("action", "retrieve")
    if action in ("retrieve", "direct_answer", "tool_use"):
        return action
    return "retrieve"  # Fallback for unexpected values
```

---

## 4. Node Implementations

### 4.1 Planner Node (`nodes/planner.py`)

**Purpose:** Analyze the incoming query, refine it for retrieval, decide routing.

**Prompt strategy:** Structured JSON output with `json_mode=True` forces deterministic response format.

```
System prompt:
  You are a judicial legal research planner for Kenya's court system.
  Analyze the query and output a JSON with:
  - "action": "retrieve" | "direct_answer" | "tool_use"
  - "refined_query": improved version of the query for vector search
  - "legal_domain": "land_law" | "criminal" | "family" | "commercial" | "constitutional" | "general"
  - "reasoning": brief explanation of routing decision

User prompt:
  Query: {current_query}
  Recent messages: {last_2_messages}
```

**Routing logic:**
| Condition | Action |
|-----------|--------|
| Query needs case law search | `retrieve` |
| Query is simple/factual/conversational | `direct_answer` |
| Query needs calculation or tool | `tool_use` |
| Parse failure / unexpected JSON | `retrieve` (fallback) |

**State update:**
```python
return {
    "current_query": planner_output["refined_query"],
    "plan": [planner_output["reasoning"]],
    "action": planner_output["action"],
    "tool_choice": planner_output.get("tool_choice", ""),
    "tool_input": planner_output.get("tool_input", ""),
}
```

**Observability:**
- Emits `NODE_LATENCY` metric: `node="planner"`
- Structured log: `{"node": "planner", "action": "retrieve", "legal_domain": "land_law"}`

---

### 4.2 Retriever Node (`nodes/retriever.py`)

**Purpose:** Perform hybrid retrieval from Qdrant (vector) and Neo4j (graph) in parallel.

**Embedding optimization:** Checks `state["query_vector"]` first. If populated (from cache miss check), reuses it. Otherwise calls Ollama to embed.

```python
async def retrieve_node(state: AgentState) -> dict:
    query = state["current_query"]

    # Reuse embedding if already computed
    if state.get("query_vector"):
        vector = state["query_vector"]
    else:
        vector = await embeddings_client.embed(query)

    # Parallel retrieval
    vector_task = asyncio.create_task(qdrant_client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=vector,
        limit=5
    ))
    graph_task = asyncio.create_task(neo4j_client.query(
        FULLTEXT_SEARCH_CYPHER,
        {"query": query}
    ))

    vector_results, graph_results = await asyncio.gather(
        vector_task, graph_task, return_exceptions=True
    )

    # Format and deduplicate
    docs = deduplicate(
        format_vector_results(vector_results) +
        format_graph_results(graph_results)
    )

    return {"documents": docs}
```

**Deduplication logic:**
```python
def deduplicate(docs: list[str]) -> list[str]:
    seen = set()
    unique = []
    for doc in docs:
        # Normalize: strip [Source: ...] suffix before comparison
        key = doc.split("[Source:")[0].strip()
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique
```

**Document format:**
```
"The test for adverse possession requires the claimant to prove:
 (1) actual possession, (2) open and notorious possession...
 [Source: Supreme Court, [2023] KESC 45]"
```

**Observability:**
- `NODE_LATENCY{node="retriever"}`
- `RETRIEVAL_DOCS{source="vector"}`, `{source="graph"}`, `{source="combined"}`

---

### 4.3 Responder Node (`nodes/responder.py`)

**Purpose:** Synthesize a cited legal answer from retrieved context.

**Prompt structure (IRAC framework):**
```
System:
  You are a judicial research assistant for Kenya's court system.
  Use the IRAC framework (Issue, Rule, Application, Conclusion).
  Always cite specific cases and statutes.
  Do not speculate beyond the provided context.

Context documents:
  [1] {doc_1}
  [2] {doc_2}
  ...

Conversation history:
  {last_4_messages}

User: {current_query}
```

**LLM settings:**
```python
await ollama_client.generate_streaming(
    messages=prompt_messages,
    temperature=0.3,    # Low randomness for legal accuracy
    max_tokens=1024
)
```

**Streaming:** The responder streams tokens directly to the FastAPI response using `async for chunk in generate_streaming(...)`.

---

### 4.4 Tool Node (`nodes/tool.py`)

**Purpose:** Execute registered tools when the planner routes to `tool_use`.

**Currently registered tools:**
| Tool | Input | Output |
|------|-------|--------|
| `calculator` | Mathematical expression | Computed result |
| (Future: `predict_case_duration`) | Case metadata | Predicted timeline |

**Tool invocation pattern:**
```python
TOOLS = {
    "calculator": calculator_tool,
    # Add new tools here
}

async def tool_node(state: AgentState) -> dict:
    tool_name = state["tool_choice"]
    tool_input = state["tool_input"]

    if tool_name not in TOOLS:
        result = f"Unknown tool: {tool_name}"
    else:
        result = await TOOLS[tool_name](tool_input)

    # Append tool result as message for responder context
    return {
        "messages": [{"role": "tool", "content": result}],
        "documents": [result]
    }
```

---

## 5. Streaming from LangGraph to Client

The chat route uses `astream_events()` to stream agent node completions as NDJSON:

```python
# In routes/chat.py
async def stream_agent():
    async for event in agent_graph.astream_events(initial_state, version="v1"):
        event_type = event["event"]

        if event_type == "on_chain_start":
            node_name = event.get("name", "")
            if node_name in ("planner", "retriever", "responder", "tool"):
                yield f'{{"event":"status","node":"{node_name}"}}\n'

        elif event_type == "on_chain_stream":
            # Token-level streaming from responder
            if event.get("name") == "responder":
                chunk = event["data"].get("chunk", "")
                if chunk:
                    yield f'{{"event":"answer","content":{json.dumps(chunk)}}}\n'

return StreamingResponse(
    stream_agent(),
    media_type="application/x-ndjson"
)
```

---

## 6. Error Handling in Agent

| Error Scenario | Behavior |
|---------------|---------|
| Planner JSON parse failure | Log warning, fallback `action="retrieve"` |
| Qdrant search timeout | Return empty vector results, continue with graph only |
| Neo4j query failure | Return empty graph results, continue with vector only |
| Both retrieval sources fail | Responder answers from conversation history + LLM knowledge |
| Ollama LLM timeout | Return error event in NDJSON stream |
| Ollama retry (3x) | Exponential backoff via `libs/retry/backoff.py` |

---

## 7. Performance Characteristics

| Operation | Expected Latency | Notes |
|-----------|----------------|-------|
| JWT validation | < 1ms | In-memory decode |
| Query embedding (Ollama) | 200-500ms | nomic-embed-text |
| Semantic cache lookup (Qdrant) | 20-50ms | gRPC transport |
| Planner LLM call (Ollama) | 500ms-2s | JSON mode, temp=0 |
| Vector search (Qdrant) | 20-50ms | Top-5, cosine |
| Graph search (Neo4j) | 50-200ms | Fulltext + 1-hop |
| Responder LLM streaming (Ollama) | 2-8s | llama3.3, 1024 tokens |
| **Total (cache miss)** | **3-11s** | TTFB ~3s (status events), full response 6-11s |
| **Total (cache hit)** | **< 100ms** | Embed + search + stream |

---

## 8. Legal Research Graph (`agents/legal_research_graph.py`)

A second, dedicated LangGraph graph used exclusively by the `POST /api/v1/legal-research` endpoint.

### Why a separate graph?

The generic chat graph (`graph.py`) includes a planner node that can short-circuit to `direct_answer`. For formal judicial research, this is undesirable — every query **must** retrieve from Kenya Law Reports and return cited authorities. The dedicated graph enforces this invariant by removing the planner.

### Topology

```
              Entry
                │
                ▼
     ┌─────────────────────┐
     │  RETRIEVER NODE     │
     │  (jurisdiction-     │
     │   filter-aware)     │
     └──────────┬──────────┘
                │
     ┌──────────▼──────────┐
     │  RESPONDER NODE     │
     │  (emits structured  │
     │   citations)        │
     └──────────┬──────────┘
                │
               END
```

### Key differences from the chat graph

| Aspect | Chat graph | Legal research graph |
|--------|-----------|----------------------|
| Planner node | Yes (can short-circuit) | No — always retrieves |
| Jurisdiction filtering | Not supported | `jurisdiction_filter` from state applied as Qdrant payload filter |
| Citations in response | Not included | `citations: list[dict]` extracted by retriever, emitted in answer event |
| Tool node | Supported | Not included |
| Cache behaviour | Semantic cache check before graph | Same semantic cache check |

### Jurisdiction filter application

The retriever node in `legal_research_graph.py` reads `state["jurisdiction_filter"]` and builds a Qdrant `Filter` condition restricting results to matching courts:

```python
# Pseudocode — see retriever node implementation
if jurisdiction_filter:
    qdrant_filter = Filter(must=[
        FieldCondition(key="court", match=MatchAny(any=jurisdiction_filter))
    ])
else:
    qdrant_filter = None  # No filter = all courts

results = qdrant_client.search(
    collection_name="kenya_law_reports",
    query_vector=vector,
    query_filter=qdrant_filter,
    limit=5,
)
```

### Citation extraction

The retriever node populates `state["citations"]` with structured metadata from each Qdrant result:

```python
citations = [
    {
        "text": hit.payload["text"],
        "source": hit.payload["source"],
        "case_number": hit.payload.get("case_number", ""),
        "court": hit.payload.get("court", ""),
    }
    for hit in vector_results
]
```

These citations are passed through to the route handler and emitted in the final `answer` event of the NDJSON stream.

---

## 9. LangGraph Version Notes

The implementation uses **LangGraph v0.1.x** patterns:
- `StateGraph` with `TypedDict` state
- `Annotated` reducers for merge behavior
- `astream_events()` with `version="v1"` for streaming
- `set_entry_point()` (older API; in newer versions use `add_edge(START, ...)`)

**Review note:** Consider migrating to `graph.add_edge(START, "planner")` pattern for LangGraph 0.2+ compatibility.
