# pipelines/ingestion/embedding/compute.py
from typing import Any

import httpx


class BatchEmbedder:
    """
    Callable Class for Ray Data.
    Maintains a session for efficiency.
    """

    def __init__(self):
        # We hardcode internal DNS for Ray Service
        self.endpoint = "http://ray-serve-embed:8000/embed"
        self.client = httpx.Client(timeout=30.0)

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        """
        Receives a batch of text chunks.
        Returns the batch with 'embedding' field added.
        """
        texts = batch["text"]

        try:
            response = self.client.post(
                self.endpoint, json={"text": texts, "task_type": "document"}
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]

            # Add embeddings to the batch dictionary
            batch["vector"] = embeddings
            return batch

        except Exception as e:
            # In Ray, raising exception triggers retry logic automatically
            raise e
