# libs/observability/metrics.py
from prometheus_client import Counter, Histogram

# ── Request Metrics ────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "rag_api_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "rag_api_latency_seconds",
    "End-to-end HTTP request latency",
    ["endpoint"],
)

# ── Cache Metrics ──────────────────────────────────────────────────────────

CACHE_HITS = Counter(
    "rag_semantic_cache_total",
    "Semantic cache hit and miss counts",
    ["result"],  # "hit" | "miss"
)

# ── LLM / Token Metrics ────────────────────────────────────────────────────

TOKEN_USAGE = Counter(
    "rag_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "type"],  # type = "prompt" | "completion"
)

# ── Agent Node Metrics ─────────────────────────────────────────────────────

NODE_LATENCY = Histogram(
    "rag_node_latency_seconds",
    "LangGraph agent node execution latency",
    ["node"],  # "planner" | "retriever" | "responder" | "tool"
)

# ── Retrieval Metrics ──────────────────────────────────────────────────────

RETRIEVAL_DOCS = Histogram(
    "rag_retrieval_docs_count",
    "Number of documents returned per retrieval source",
    ["source"],  # "vector" | "graph" | "combined"
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)


# ── Helpers ────────────────────────────────────────────────────────────────

def track_request(method: str, endpoint: str, status: int) -> None:
    """Increment the HTTP request counter."""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
