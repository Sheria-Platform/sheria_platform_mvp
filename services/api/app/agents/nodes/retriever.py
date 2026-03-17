# services/api/app/agents/nodes/retriever.py
"""LangGraph Retriever node — Hybrid RAG implementation.

Performs two retrieval strategies in parallel and merges the results:

1. **Vector search** (Qdrant) — semantic similarity over embedded chunks
   of Kenya Law Reports, judgments, and statutes.
2. **Graph search** (Neo4j) — fulltext entity lookup followed by a
   one-hop neighbourhood expansion to surface structural relationships
   (case citations, legal principles, etc.).

The two result sets are deduplicated via :func:`_dedup` (content-aware,
ignores ``[Source: ...]`` suffix differences) before being stored in
``state["documents"]`` for the responder node to synthesise.

Example:
    For query ``"adverse possession continuous possession Kenya"``:

    * Qdrant returns 5 chunk excerpts from matching judgments.
    * Neo4j returns 5 triples such as
      ``"Muiruri v Republic CITES adverse_possession"``.
    * Combined: up to 10 unique strings passed to the LLM as context.
"""

import asyncio
import logging
import time

from qdrant_client.http import models as qdrant_models

from libs.observability.metrics import RETRIEVAL_DOCS
from services.api.app.agents.state import AgentState
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_embeddings import embeddings_client
from services.api.app.clients.qdrant import qdrant_client

logger = logging.getLogger(__name__)

# Cypher for one-hop entity neighbourhood search via fulltext index
_GRAPH_CYPHER = """
CALL db.index.fulltext.queryNodes("entity_index", $query)
YIELD node, score
MATCH (node)-[r]->(neighbor)
RETURN node.name + ' ' + type(r) + ' ' + neighbor.name AS text
LIMIT 5
"""


def _dedup(docs: list[str]) -> list[str]:
    """Deduplicate documents by text content, ignoring trailing bracket annotations.

    Strips any ``" [..."`` suffix before comparison so the same text with
    different source or citation annotations is still treated as a duplicate.

    Args:
        docs: List of document strings, optionally ending with
            ``" [Source: <filename>]"`` or ``" [Citation: ...]"``.

    Returns:
        Deduplicated list preserving insertion order and original strings.
    """
    seen: set[str] = set()
    result: list[str] = []
    for doc in docs:
        key = doc.split(" [")[0].strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(doc)
    return result


async def retrieve_node(state: AgentState) -> dict:
    """Embed the query and run vector + graph search in parallel.

    Steps:
        1. Reuse ``state["query_vector"]`` if present (set by the chat route
           during the semantic cache check), otherwise embed fresh via Ollama.
        2. Launch Qdrant ANN search and Neo4j fulltext search
           concurrently with ``asyncio.gather``.
        3. Merge and deduplicate results via :func:`_dedup`.
        4. Return the combined document list.

    Args:
        state: Current agent state.  Must contain ``"current_query"``.
            If ``"query_vector"`` is a non-empty list, the embed call is
            skipped entirely.

    Returns:
        A partial state dict with key:
            - ``"documents"`` (list[str]): Combined retrieval results,
              each formatted as
              ``"<text> [Source: <filename>]"`` for vector hits or
              ``"<entity> <rel> <neighbor>"`` for graph hits.

    Note:
        Graph search failures are caught silently and return an empty
        list so vector search results are never lost.
    """
    query: str = state["current_query"]
    logger.info("Retriever node started", extra={"node": "retriever"})
    node_start = time.perf_counter()

    # Step 1: Reuse cached vector from state, or embed fresh
    cached_vector: list[float] = state.get("query_vector") or []
    embed_ms = 0.0
    if cached_vector:
        query_vector = cached_vector
        logger.debug(
            "Retriever reusing cached query vector", extra={"node": "retriever"}
        )
    else:
        embed_start = time.perf_counter()
        query_vector = await embeddings_client.embed_query(query)
        embed_ms = round((time.perf_counter() - embed_start) * 1000, 2)
        logger.debug(
            "Query embedded",
            extra={"node": "retriever", "duration_ms": embed_ms},
        )

    # Step 2: Parallel retrieval ──────────────────────────────────────

    jurisdiction_filter: list[str] = state.get("jurisdiction_filter") or []

    async def _vector_search() -> tuple[list[str], list[dict]]:
        """Search Qdrant and format results with structured Kenya Law citations.

        Returns:
            Tuple of (doc_strings, citation_dicts).  doc_strings include the
            citation metadata inline so the LLM can use it directly.
            citation_dicts are structured for the API response payload.
        """
        # Build payload filter for jurisdiction if specified
        q_filter = None
        if jurisdiction_filter:
            q_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="court_name",
                        match=qdrant_models.MatchAny(any=jurisdiction_filter),
                    )
                ]
            )

        results = await qdrant_client.search(
            vector=query_vector, limit=5, query_filter=q_filter
        )
        docs: list[str] = []
        citations: list[dict] = []
        for r in results:
            text = r.payload.get("text", "")
            citation_code = r.payload.get("citation_code", "")
            court_name = r.payload.get("court_name", "")
            year = r.payload.get("year", "")
            case_slug = r.payload.get("case_slug", "")
            score = round(r.score, 4)

            # Inline citation for the LLM context
            docs.append(
                f"{text} [Citation: {citation_code} | Court: {court_name} | Year: {year}]"
            )
            # Structured citation for the API response
            citations.append(
                {
                    "citation_code": citation_code,
                    "court_name": court_name,
                    "year": year,
                    "case_slug": case_slug,
                    "score": score,
                }
            )
        return docs, citations

    async def _graph_search() -> list[str]:
        """Search Neo4j fulltext index for entity relationships."""
        try:
            rows = await neo4j_client.query(_GRAPH_CYPHER, {"query": query})
            return [row["text"] for row in rows]
        except Exception:
            logger.exception(
                "Graph search failed",
                extra={"node": "retriever"},
            )
            return []

    retrieval_start = time.perf_counter()
    (vector_docs, structured_citations), graph_docs = await asyncio.gather(
        _vector_search(), _graph_search()
    )
    retrieval_ms = round((time.perf_counter() - retrieval_start) * 1000, 2)

    # Step 3: Merge with content-aware deduplication
    combined: list[str] = _dedup(vector_docs + graph_docs)
    total_ms = round((time.perf_counter() - node_start) * 1000, 2)

    # Track retrieval counts in Prometheus
    RETRIEVAL_DOCS.labels(source="vector").observe(len(vector_docs))
    RETRIEVAL_DOCS.labels(source="graph").observe(len(graph_docs))
    RETRIEVAL_DOCS.labels(source="combined").observe(len(combined))

    logger.info(
        "Retriever node completed",
        extra={
            "node": "retriever",
            "vector_docs": len(vector_docs),
            "graph_docs": len(graph_docs),
            "combined_docs": len(combined),
            "jurisdiction_filter": jurisdiction_filter,
            "embed_ms": embed_ms,
            "retrieval_ms": retrieval_ms,
            "duration_ms": total_ms,
        },
    )

    return {"documents": combined, "citations": structured_citations}
