# services/api/app/cache/semantic.py
import logging

from services.api.app.clients.ollama_embeddings import embeddings_client  # Replaces ray_embed
from services.api.app.clients.qdrant import qdrant_client

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Implements Semantic Caching using Vector Search.
    Instead of exact string matching, we match by meaning.
    """

    async def get_cached_response(
        self, query: str, threshold: float = 0.95
    ) -> str | None:
        """
        Check if a similar query exists in the cache.
        """
        try:
            # 1. Embed the incoming query via Ollama (replaces Ray Serve embed_client)
            vector = await embeddings_client.embed_query(query)

            # 2. Search in the 'semantic_cache' collection in Qdrant
            results = await qdrant_client.client.search(
                collection_name="semantic_cache",
                query_vector=vector,
                limit=1,
                with_payload=True,
                score_threshold=threshold,  # Only extremely similar queries
            )

            if results:
                logger.info("Semantic Cache Hit! Score: %s", results[0].score)
                return results[0].payload["answer"]

        except Exception as e:
            logger.warning("Semantic cache lookup failed: %s", e)

        return None

    async def set_cached_response(self, query: str, answer: str):
        """
        Save a Q&A pair to the cache.
        """
        try:
            import uuid

            from qdrant_client.http import models

            # 1. Embed query via Ollama (replaces Ray Serve embed_client)
            vector = await embeddings_client.embed_query(query)

            # 2. Save to Vector DB
            await qdrant_client.client.upsert(
                collection_name="semantic_cache",
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={"query": query, "answer": answer},
                    )
                ],
            )
        except Exception as e:
            logger.warning("Failed to write to semantic cache: %s", e)


semantic_cache = SemanticCache()
