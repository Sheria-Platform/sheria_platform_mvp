from typing import Any
import os

ENV = os.getenv("ENV", "dev")  

if ENV == "dev":
    from langchain_community.embeddings import OllamaEmbeddings
else:
    import httpx

class BatchEmbedder:
    """
    Handles embeddings for both dev (local) and prod (Ray Serve)
    """

    def __init__(self, endpoint: str = None):
        self.env = ENV

        if self.env == "dev":
            # Use Ollama embeddings locally
            self.embedder = OllamaEmbeddings(model="nomic-embed-text")
        else:
            # Use Ray Serve in prod
            self.endpoint = endpoint or "http://ray-serve-embed:8000/embed"
            self.client = httpx.Client(timeout=30.0)

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        texts = batch["text"]

        if self.env == "dev":
            embeddings = [self.embedder.embed_query(t) for t in texts]
        else:
            response = self.client.post(
                self.endpoint,
                json={"text": texts, "task_type": "document"}
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]

        batch["vector"] = embeddings
        return batch
