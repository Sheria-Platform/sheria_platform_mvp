# pipelines/ingestion/embedding/embedding_compute.py
import os
from typing import Any

import httpx


class BatchEmbedder:
    """
    Callable Class for Ray Data.
    Uses Ollama for generating embeddings.
    """

    def __init__(self):
        # Use full endpoint URL or construct from host
        self.endpoint = os.getenv(
            "OLLAMA_EMBED_ENDPOINT",
            "http://localhost:11436/api/embeddings"
        )
        self.model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.client = httpx.Client(timeout=120.0)

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        """
        Receives a batch of text chunks.
        Returns the batch with 'embedding' field added.

        Uses Ollama's embeddings API which processes one text at a time.
        For batch processing, we iterate and collect results.
        """
        texts = batch["text"]
        embeddings = []

        try:
            # Process each text individually (Ollama doesn't support batch in single call)
            for text in texts:
                response = self.client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "prompt": text
                    }
                )
                response.raise_for_status()
                embedding = response.json()["embedding"]
                embeddings.append(embedding)

            # Add embeddings to the batch dictionary
            batch["vector"] = embeddings
            return batch

        except Exception as e:
            # In Ray, raising exception triggers retry logic automatically
            print(f"Embedding generation failed: {e}")
            raise e
