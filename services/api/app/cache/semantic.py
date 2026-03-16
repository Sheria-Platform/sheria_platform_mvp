# services/api/app/cache/semantic.py
import logging
import time

from services.api.app.clients.ollama_embeddings import embeddings_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.config import settings

logger = logging.getLogger(__name__)


class SemanticCache:
    """Semantic cache backed by Qdrant with vector reuse and TTL filtering.

    Key optimizations vs the original implementation:
    - ``get_cached_response`` returns ``(answer, vector)`` so the caller can
      reuse the embedding vector downstream without re-embedding.
    - ``set_cached_response`` accepts an optional pre-computed ``vector`` to
      skip a redundant Ollama embed call.
    - Cache entries include a ``created_at`` UNIX timestamp; entries older than
      ``max_age_days`` are ignored during lookup, preventing stale legal answers
      from being returned indefinitely.
    """

    async def get_cached_response(
        self,
        query: str,
        threshold: float = 0.95,
        max_age_days: int | None = None,
    ) -> tuple[str | None, list[float] | None]:
        """Search for a semantically similar cached answer.

        Args:
            query: The user's query text.
            threshold: Minimum cosine similarity score to count as a hit.
            max_age_days: Ignore cache entries older than this many days.

        Returns:
            A ``(answer, vector)`` tuple.  ``answer`` is ``None`` on a cache
            miss.  ``vector`` is always returned (even on a miss) so the caller
            can reuse it for retrieval without a second embed call.
        """
        effective_max_age = (
            max_age_days
            if max_age_days is not None
            else settings.SEMANTIC_CACHE_MAX_AGE_DAYS
        )
        vector: list[float] | None = None
        try:
            vector = await embeddings_client.embed_query(query)

            from qdrant_client.http import models as qmodels

            cutoff = time.time() - (effective_max_age * 86400)
            results = await qdrant_client.client.search(
                collection_name="semantic_cache",
                query_vector=vector,
                limit=1,
                with_payload=True,
                score_threshold=threshold,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="created_at",
                            range=qmodels.Range(gte=cutoff),
                        )
                    ]
                ),
            )

            if results:
                logger.info("Semantic Cache Hit! Score: %s", results[0].score)
                return results[0].payload["answer"], vector

        except Exception as e:
            logger.warning("Semantic cache lookup failed: %s", e)

        return None, vector

    async def set_cached_response(
        self,
        query: str,
        answer: str,
        vector: list[float] | None = None,
    ) -> None:
        """Persist a Q&A pair to the semantic cache.

        Args:
            query: The user's query text.
            answer: The assistant's answer to cache.
            vector: Pre-computed embedding for ``query``.  When provided,
                skips the Ollama embed call entirely.
        """
        try:
            import uuid

            from qdrant_client.http import models

            if vector is None:
                vector = await embeddings_client.embed_query(query)

            await qdrant_client.client.upsert(
                collection_name="semantic_cache",
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "query": query,
                            "answer": answer,
                            "created_at": time.time(),
                        },
                    )
                ],
            )
        except Exception as e:
            logger.warning("Failed to write to semantic cache: %s", e)


semantic_cache = SemanticCache()
