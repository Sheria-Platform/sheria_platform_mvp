# pipelines/ingestion/embedding/embedding_compute.py
"""
Embedding generation module for Sheria Platform ingestion pipeline.

This module provides the BatchEmbedder class which generates vector embeddings
for text chunks using Ollama's embedding API. All texts in a batch are embedded
concurrently via asyncio.gather, so batch latency is bounded by the slowest
single request rather than the sum of all requests.

Environment Variables:
    OLLAMA_EMBED_ENDPOINT: Ollama embeddings API endpoint
    OLLAMA_EMBED_MODEL: Model name for embeddings (default: nomic-embed-text)
    EMBED_TIMEOUT: Request timeout in seconds (default: 120)
    EMBED_MAX_RETRIES: Maximum retry attempts (default: 3)
    EMBED_RETRY_DELAY: Initial retry delay in seconds (default: 1)
"""

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BatchEmbedder:
    """
    Generate embeddings for text chunks using Ollama API.

    All texts in a batch are embedded concurrently using an async HTTP client,
    so batch latency is O(1) rather than O(n) sequential round-trips.

    Example:
        >>> embedder = BatchEmbedder()
        >>> batch = {"text": ["Hello world", "Legal document text"]}
        >>> result = embedder(batch)
        >>> print(len(result["vector"]))  # 2 vectors
        >>> embedder.close()
    """

    def __init__(self):
        """
        Initialize the BatchEmbedder with configuration from environment variables.

        Raises:
            ValueError: If endpoint or model configuration is invalid
        """
        self.endpoint = os.getenv(
            "OLLAMA_EMBED_ENDPOINT", "http://192.168.214.22:11436/api/embeddings"
        )
        self.model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.timeout = float(os.getenv("EMBED_TIMEOUT", "120"))
        self.max_retries = int(os.getenv("EMBED_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("EMBED_RETRY_DELAY", "1"))

        if not self.endpoint or not self.endpoint.startswith("http"):
            raise ValueError(f"Invalid OLLAMA_EMBED_ENDPOINT: {self.endpoint}")
        if not self.model:
            raise ValueError("OLLAMA_EMBED_MODEL cannot be empty")
        if self.timeout <= 0 or self.timeout > 600:
            raise ValueError(
                f"EMBED_TIMEOUT must be between 0 and 600, got {self.timeout}"
            )

        logger.info(
            f"BatchEmbedder initialized: endpoint={self.endpoint}, "
            f"model={self.model}, timeout={self.timeout}s"
        )

    async def _embed_one(
        self,
        client: httpx.AsyncClient,
        text: str,
        idx: int,
    ) -> tuple[int, list[float] | None]:
        """
        Embed a single text with retry logic.

        Returns:
            (idx, embedding) — embedding is None if all retries failed.
        """
        if not text or not isinstance(text, str):
            logger.warning(f"Skipping invalid text at index {idx}: {type(text)}")
            return idx, None

        last_error = None
        for attempt in range(self.max_retries):
            try:
                # /api/embed (Ollama >= 0.1.26) uses "input"
                # /api/embeddings (older Ollama) uses "prompt"
                use_new_api = (
                    "/api/embed" in self.endpoint
                    and "/api/embeddings" not in self.endpoint
                )
                payload = {
                    "model": self.model,
                    "input" if use_new_api else "prompt": text[:8192],
                }
                response = await client.post(self.endpoint, json=payload)
                response.raise_for_status()
                response_data = response.json()

                # New API: {"embeddings": [[...float...]]}
                # Old API: {"embedding": [...float...]}
                if "embeddings" in response_data:
                    embeddings_array = response_data["embeddings"]
                    if not embeddings_array or not isinstance(embeddings_array, list):
                        raise ValueError(
                            f"Invalid embeddings format: {type(embeddings_array)}"
                        )
                    embedding = embeddings_array[0]
                elif "embedding" in response_data:
                    embedding = response_data["embedding"]
                else:
                    raise ValueError(
                        "Invalid response: missing 'embeddings' or 'embedding' field"
                    )

                if not embedding or not isinstance(embedding, list):
                    raise ValueError(f"Invalid embedding vector: {type(embedding)}")

                return idx, embedding

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    f"Embedding timeout for text {idx} (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    f"HTTP error for text {idx} (attempt {attempt + 1}/{self.max_retries}): "
                    f"{e.response.status_code}"
                )
                if e.response.status_code < 500:
                    break  # Client error — don't retry
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Embedding failed for text {idx} (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))

        logger.error(
            f"Failed to generate embedding for text {idx} after {self.max_retries} attempts: {last_error}"
        )
        return idx, None

    async def _embed_all(
        self, texts: list[str]
    ) -> list[tuple[int, list[float] | None]]:
        """Fire all embedding requests concurrently and return results in input order."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [
                self._embed_one(client, text, idx) for idx, text in enumerate(texts)
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        """
        Generate embeddings for a batch of text chunks (concurrently).

        Args:
            batch: Dictionary with "text": List[str] and optional "metadata".

        Returns:
            Input dict with "vector": List[Optional[List[float]]] added.

        Raises:
            ValueError: If batch structure is invalid.
            Exception: If every single embedding in the batch fails.
        """
        if "text" not in batch:
            raise ValueError("Batch must contain 'text' field")

        texts = batch["text"]
        if not isinstance(texts, list):
            raise ValueError(f"Batch 'text' must be a list, got {type(texts)}")

        if not texts:
            logger.warning("Empty text list provided, returning empty embeddings")
            batch["vector"] = []
            return batch

        raw_results = asyncio.run(self._embed_all(texts))

        embeddings: list[list[float] | None] = []
        failed_indices: list[int] = []

        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                logger.error(f"Unexpected exception for text {i}: {result}")
                embeddings.append(None)
                failed_indices.append(i)
            else:
                _, embedding = result
                embeddings.append(embedding)
                if embedding is None:
                    failed_indices.append(i)

        if len(failed_indices) == len(texts):
            raise Exception(f"All {len(texts)} embeddings failed in batch.")

        if failed_indices:
            logger.warning(
                f"Failed to generate {len(failed_indices)}/{len(texts)} embeddings"
            )

        batch["vector"] = embeddings
        return batch

    def close(self) -> None:
        """No-op — async implementation uses per-call clients with context managers."""
        logger.debug("BatchEmbedder close() called")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
