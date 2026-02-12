# pipelines/ingestion/graph/extractor_graph.py
import json
import os
from typing import Any

import httpx

from pipelines.ingestion.graph.schema_graph import GraphSchema


class GraphExtractor:
    """
    Ray Actor Class for Graph Extraction.
    Uses Ollama for LLM-based entity and relationship extraction.
    """

    def __init__(self):
        # Use Ollama endpoint (configurable via environment)
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.llm_endpoint = f"{ollama_host}/api/chat"
        self.model = os.getenv("OLLAMA_LLM_MODEL", "llama3")
        self.client = httpx.Client(timeout=120.0)  # Long timeout for reasoning

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        """
        Process a batch of text chunks.
        Uses Ollama's chat API to extract graph entities and relationships.
        """
        nodes_list = []
        edges_list = []

        # Iterate through chunks in the batch
        for text in batch["text"]:
            try:
                # 1. Construct Prompt
                prompt = f"""
                {GraphSchema.get_system_prompt()}

                Input Text:
                {text}
                """

                # 2. Call Ollama LLM
                response = self.client.post(
                    self.llm_endpoint,
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a knowledge graph extraction assistant. Extract entities and relationships from the given text and return ONLY valid JSON."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.0,  # Deterministic output
                            "num_predict": 1024,  # Max tokens
                        },
                        "format": "json"  # Request JSON response format
                    },
                )
                response.raise_for_status()

                # 3. Parse JSON Output
                # Extract content from Ollama response
                content = response.json()["message"]["content"]

                # Try to parse as JSON
                try:
                    graph_data = json.loads(content)
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract JSON from markdown code blocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                        graph_data = json.loads(content)
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                        graph_data = json.loads(content)
                    else:
                        raise

                # 4. Append to results
                nodes_list.append(graph_data.get("nodes", []))
                edges_list.append(graph_data.get("edges", []))

            except Exception as e:
                # Log error but don't crash the pipeline; return empty graph for this chunk
                print(f"Graph extraction failed for chunk: {e}")
                nodes_list.append([])
                edges_list.append([])

        # Add graph data to the batch
        batch["graph_nodes"] = nodes_list
        batch["graph_edges"] = edges_list
        return batch
