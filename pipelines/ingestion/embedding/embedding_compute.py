# pipelines/ingestion/embedding/embedding_compute.py
"""
Embedding generation module for Sheria Platform ingestion pipeline.

This module provides the BatchEmbedder class which generates vector embeddings
for text chunks using Ollama's embedding API. It includes retry logic,
rate limiting support, and proper resource cleanup.

Environment Variables:
    OLLAMA_EMBED_ENDPOINT: Ollama embeddings API endpoint
    OLLAMA_EMBED_MODEL: Model name for embeddings (default: nomic-embed-text)
    EMBED_TIMEOUT: Request timeout in seconds (default: 120)
    EMBED_MAX_RETRIES: Maximum retry attempts (default: 3)
    EMBED_RETRY_DELAY: Initial retry delay in seconds (default: 1)
"""
import logging
import os
import time
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class BatchEmbedder:
    """
    Generate embeddings for text chunks using Ollama API.

    This class is designed to work with Ray Data map_batches operations.
    It processes batches of text chunks and adds vector embeddings to each chunk.

    Features:
        - Automatic retry with exponential backoff
        - Request timeout handling
        - Resource cleanup (HTTP client)
        - Input validation
        - Detailed error logging

    Attributes:
        endpoint (str): Ollama embeddings API endpoint URL
        model (str): Embedding model name
        timeout (float): Request timeout in seconds
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Initial retry delay in seconds
        client (httpx.Client): HTTP client for API requests

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
        # Load configuration from environment
        self.endpoint = os.getenv(
            "OLLAMA_EMBED_ENDPOINT",
            "http://192.168.214.22:11436/api/embeddings"
        )
        self.model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.timeout = float(os.getenv("EMBED_TIMEOUT", "120"))
        self.max_retries = int(os.getenv("EMBED_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("EMBED_RETRY_DELAY", "1"))

        # Validate configuration
        if not self.endpoint or not self.endpoint.startswith("http"):
            raise ValueError(f"Invalid OLLAMA_EMBED_ENDPOINT: {self.endpoint}")
        if not self.model:
            raise ValueError("OLLAMA_EMBED_MODEL cannot be empty")
        if self.timeout <= 0 or self.timeout > 600:
            raise ValueError(f"EMBED_TIMEOUT must be between 0 and 600, got {self.timeout}")

        # Initialize HTTP client
        self.client = httpx.Client(timeout=self.timeout)

        logger.info(f"BatchEmbedder initialized: endpoint={self.endpoint}, model={self.model}, timeout={self.timeout}s")

    def __call__(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate embeddings for a batch of text chunks.

        This method processes each text in the batch sequentially (Ollama doesn't
        support true batching in a single API call). Failed embeddings are retried
        with exponential backoff.

        Args:
            batch: Dictionary containing:
                - "text": List[str] - Text chunks to embed
                - "metadata": List[dict] - Optional metadata for each chunk

        Returns:
            Dictionary containing:
                - All input fields (text, metadata, etc.)
                - "vector": List[List[float]] - Generated embeddings

        Raises:
            ValueError: If batch structure is invalid
            httpx.HTTPError: If all retry attempts fail
            Exception: For other unexpected errors

        Note:
            Ollama processes one text at a time, so batch size affects latency.
            For better performance, use smaller batches with higher concurrency.
        """
        # Validate input
        if "text" not in batch:
            raise ValueError("Batch must contain 'text' field")

        texts = batch["text"]
        if not isinstance(texts, list):
            raise ValueError(f"Batch 'text' must be a list, got {type(texts)}")

        if not texts:
            logger.warning("Empty text list provided, returning empty embeddings")
            batch["vector"] = []
            return batch

        embeddings = []
        failed_indices = []

        # Process each text individually
        for idx, text in enumerate(texts):
            if not text or not isinstance(text, str):
                logger.warning(f"Skipping invalid text at index {idx}: {type(text)}")
                embeddings.append(None)
                failed_indices.append(idx)
                continue

            # Retry loop for this text
            success = False
            last_error = None

            for attempt in range(self.max_retries):
                try:
                    response = self.client.post(
                        self.endpoint,
                        json={
                            "model": self.model,
                            "input": text[:8192]  # Truncate to avoid token limits
                        }
                    )
                    response.raise_for_status()
                    response_data = response.json()

                    # Validate response structure
                    if "embeddings" not in response_data:
                        raise ValueError(f"Invalid response: missing 'embeddings' field")

                    embeddings_array = response_data["embeddings"]
                    if not embeddings_array or not isinstance(embeddings_array, list):
                        raise ValueError(f"Invalid embeddings format: {type(embeddings_array)}")

                    embedding = embeddings_array[0]
                    if not embedding or not isinstance(embedding, list):
                        raise ValueError(f"Invalid embedding vector: {type(embedding)}")

                    embeddings.append(embedding)
                    success = True
                    break

                except httpx.TimeoutException as e:
                    last_error = e
                    logger.warning(f"Embedding timeout for text {idx} (attempt {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff

                except httpx.HTTPStatusError as e:
                    last_error = e
                    logger.warning(f"HTTP error for text {idx} (attempt {attempt + 1}/{self.max_retries}): {e.response.status_code}")
                    if attempt < self.max_retries - 1 and e.response.status_code >= 500:
                        time.sleep(self.retry_delay * (2 ** attempt))
                    elif e.response.status_code < 500:
                        # Client error, don't retry
                        break

                except Exception as e:
                    last_error = e
                    logger.warning(f"Embedding failed for text {idx} (attempt {attempt + 1}/{self.max_retries}): {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))

            if not success:
                logger.error(f"Failed to generate embedding for text {idx} after {self.max_retries} attempts: {last_error}")
                embeddings.append(None)
                failed_indices.append(idx)

        # Check if all embeddings failed
        if len(failed_indices) == len(texts):
            raise Exception(f"All embeddings failed in batch. Last error: {last_error}")

        # Log partial failures
        if failed_indices:
            logger.warning(f"Failed to generate {len(failed_indices)}/{len(texts)} embeddings")

        # Add embeddings to batch
        batch["vector"] = embeddings
        return batch

    def close(self) -> None:
        """
        Clean up resources (close HTTP client).

        Should be called when the embedder is no longer needed to ensure
        proper connection cleanup.
        """
        try:
            self.client.close()
            logger.debug("BatchEmbedder HTTP client closed")
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False
