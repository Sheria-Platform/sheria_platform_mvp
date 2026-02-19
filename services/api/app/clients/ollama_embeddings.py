# services/api/app/clients/ollama_embeddings.py
"""
Ollama Embeddings Client - Replaces Ray Serve ray_embed.py.

Wraps Ollama's /api/embed endpoint with:
- Batch processing (up to 100 texts per request)
- Exponential backoff retries
- Numpy array output for Qdrant compatibility
- Short timeout (10s for single queries, 60s for batches)
"""
import logging

import httpx
import numpy as np

from libs.retry.backoff import exponential_backoff
from services.api.app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum texts per Ollama /api/embed call
_BATCH_SIZE = 100


class OllamaEmbeddingsClient:
    """
    Embeddings client backed by Ollama's /api/embed endpoint.

    Replaces RayEmbedClient from ray_embed.py. Uses per-request httpx
    clients (no persistent pool needed — embedding calls are infrequent
    and can reuse Ollama's own connection management).
    """

    def __init__(self) -> None:
        self.base_url: str = settings.OLLAMA_BASE_URL
        self.model: str = settings.OLLAMA_EMBEDDING_MODEL

    @exponential_backoff(max_retries=3, base_delay=0.5)
    async def embed_query(self, text: str) -> list[float]:
        """
        Embed a single query string and return a float vector.

        Replaces RayEmbedClient.embed_query().

        Args:
            text: The query to embed.

        Returns:
            Embedding vector as list[float].

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
            ValueError: If Ollama returns an empty embeddings list.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post(
                "/api/embed",
                json={"model": self.model, "input": text},
            )
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise ValueError("Ollama returned empty embeddings for single text.")
        return embeddings[0]

    @exponential_backoff(max_retries=3, base_delay=0.5)
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple documents, processing in batches of up to 100.

        Replaces RayEmbedClient.embed_documents().

        Args:
            texts: Document strings to embed.

        Returns:
            List of embedding vectors.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
            ValueError: On batch size mismatch.
        """
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]

            async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
                response = await client.post(
                    "/api/embed",
                    json={"model": self.model, "input": batch},
                )
                response.raise_for_status()
                data = response.json()

            batch_embeddings: list[list[float]] = data.get("embeddings", [])
            if len(batch_embeddings) != len(batch):
                raise ValueError(
                    f"Embedding count mismatch: expected {len(batch)}, "
                    f"got {len(batch_embeddings)}"
                )
            all_embeddings.extend(batch_embeddings)
            logger.debug(
                "Embedded batch %d/%d (%d vectors)",
                batch_start // _BATCH_SIZE + 1,
                (len(texts) + _BATCH_SIZE - 1) // _BATCH_SIZE,
                len(batch_embeddings),
            )

        return all_embeddings

    async def embed_numpy(self, text: str) -> np.ndarray:
        """
        Embed text and return a float32 numpy array (Qdrant-compatible).

        Args:
            text: Text to embed.

        Returns:
            Embedding as np.ndarray with dtype float32.
        """
        vector = await self.embed_query(text)
        return np.array(vector, dtype=np.float32)


# Global singleton — no lifespan management needed (per-request clients)
embeddings_client = OllamaEmbeddingsClient()
