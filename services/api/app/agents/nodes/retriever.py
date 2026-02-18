# services/api/app/agents/nodes/retriever.py
"""LangGraph Retriever node — Hybrid RAG implementation.

Performs two retrieval strategies in parallel and merges the results:

1. **Vector search** (Qdrant) — semantic similarity over embedded chunks
   of Kenya Law Reports, judgments, and statutes.
2. **Graph search** (Neo4j) — fulltext entity lookup followed by a
   one-hop neighbourhood expansion to surface structural relationships
   (case citations, legal principles, etc.).

The two result sets are deduplicated via ``set()`` before being stored
in ``state["documents"]`` for the responder node to synthesise.

Example:
    For query ``"adverse possession continuous possession Kenya"``:

    * Qdrant returns 5 chunk excerpts from matching judgments.
    * Neo4j returns 5 triples such as
      ``"Muiruri v Republic CITES adverse_possession"``.
    * Combined: up to 10 unique strings passed to the LLM as context.
"""

import asyncio
import logging

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


async def retrieve_node(state: AgentState) -> dict:
    """Embed the query and run vector + graph search in parallel.

    Steps:
        1. Embed ``state["current_query"]`` via Ollama
           (``nomic-embed-text``).
        2. Launch Qdrant ANN search and Neo4j fulltext search
           concurrently with ``asyncio.gather``.
        3. Merge and deduplicate results.
        4. Return the combined document list.

    Args:
        state: Current agent state.  Must contain ``"current_query"``.

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
    logger.info("Retriever Node: query=%s", query)

    # Step 1: Embed query via Ollama (sequential — Qdrant needs it)
    query_vector: list[float] = await embeddings_client.embed_query(query)

    # Step 2: Parallel retrieval ──────────────────────────────────────

    async def _vector_search() -> list[str]:
        """Search Qdrant and format results with source attribution."""
        results = await qdrant_client.search(vector=query_vector, limit=5)
        docs = []
        for r in results:
            text = r.payload.get("text", "")
            # Payload shape varies by ingestion pipeline; try common locations
            filename = (
                r.payload.get("metadata", {}).get("filename")
                or r.payload.get("source")
                or r.payload.get("filename")
                or "unknown"
            )
            docs.append(f"{text} [Source: {filename}]")
        return docs

    async def _graph_search() -> list[str]:
        """Search Neo4j fulltext index for entity relationships."""
        try:
            rows = await neo4j_client.query(
                _GRAPH_CYPHER, {"query": query}
            )
            return [row["text"] for row in rows]
        except Exception as exc:
            logger.error("Graph search failed: %s", exc)
            return []

    vector_docs, graph_docs = await asyncio.gather(
        _vector_search(), _graph_search()
    )

    # Step 3: Merge and deduplicate
    combined: list[str] = list(set(vector_docs + graph_docs))
    logger.info(
        "Retriever Node: %d docs (vector=%d, graph=%d)",
        len(combined),
        len(vector_docs),
        len(graph_docs),
    )

    return {"documents": combined}
