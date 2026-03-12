# pipelines/ingestion/graph/extractor_graph.py
"""
Graph extraction module for Sheria Platform ingestion pipeline.

This module provides the GraphExtractor class which extracts legal entities
and relationships from text chunks using Ollama's LLM API. It includes retry
logic, JSON parsing robustness, and proper resource cleanup.

Environment Variables:
    OLLAMA_LLM_ENDPOINT: Ollama chat API endpoint
    OLLAMA_LLM_MODEL: Model name for LLM (default: llama3)
    LLM_TIMEOUT: Request timeout in seconds (default: 180)
    LLM_MAX_RETRIES: Maximum retry attempts (default: 3)
    LLM_RETRY_DELAY: Initial retry delay in seconds (default: 2)
    LLM_TEMPERATURE: LLM temperature for deterministic output (default: 0.0)
    LLM_MAX_TOKENS: Maximum tokens for generation (default: 4096)
    GRAPH_CONCURRENCY: Max concurrent LLM requests in-flight (default: 10)
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from pipelines.ingestion.graph.schema_graph import GraphSchema, VALID_NODE_LABELS, VALID_RELATION_TYPES as _SCHEMA_RELATION_TYPES

logger = logging.getLogger(__name__)

# JSON schema for constrained decoding via Ollama's format field.
# Guarantees the LLM always returns {"nodes": [...], "edges": [...]} structure,
# even for short or non-legal chunks that would otherwise produce explanatory text.
# Enum constraints on `type` fields force the model to only produce valid schema
# values, eliminating "Skipping edge with unknown relationship type" warnings.
_NODE_TYPE_ENUM = list(VALID_NODE_LABELS.__args__)
_RELATION_TYPE_ENUM = list(_SCHEMA_RELATION_TYPES.__args__)

GRAPH_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": _NODE_TYPE_ENUM}
                },
                "required": ["id", "type"]
            }
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string", "enum": _RELATION_TYPE_ENUM}
                },
                "required": ["source", "target", "type"]
            }
        }
    },
    "required": ["nodes", "edges"]
}


class GraphExtractor:
    """
    Extract legal entities and relationships from text using LLM.

    This class uses Ollama's chat API to extract structured graph data (nodes
    and edges) from legal text chunks. It enforces a predefined schema and
    handles JSON parsing robustness.

    Features:
        - Concurrent LLM requests via asyncio.gather (batch latency = slowest chunk,
          not sum of all chunks)
        - Semaphore-bounded concurrency to avoid overwhelming the Ollama server
        - Automatic retry with exponential backoff
        - Robust JSON parsing (handles markdown code blocks)
        - Schema validation
        - Request timeout handling
        - Detailed error logging

    Attributes:
        llm_endpoint (str): Ollama chat API endpoint URL
        model (str): LLM model name
        timeout (float): Request timeout in seconds
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Initial retry delay in seconds
        temperature (float): LLM temperature (0.0 for deterministic)
        max_tokens (int): Maximum tokens for generation
        concurrency (int): Max simultaneous LLM requests (GRAPH_CONCURRENCY env var)

    Example:
        >>> extractor = GraphExtractor()
        >>> batch = {"text": ["Kenya Supreme Court case..."]}
        >>> result = extractor(batch)
        >>> print(result["graph_nodes"])  # [[{id, type}, ...]]
        >>> extractor.close()
    """

    def __init__(self):
        """
        Initialize the GraphExtractor with configuration from environment variables.

        Raises:
            ValueError: If endpoint or model configuration is invalid
        """
        # Load configuration from environment
        self.llm_endpoint = os.getenv(
            "OLLAMA_LLM_ENDPOINT",
            "http://192.168.214.22:11435/api/chat"
        )
        self.model = os.getenv("OLLAMA_LLM_MODEL", "llama3")
        self.timeout = float(os.getenv("LLM_TIMEOUT", "180"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("LLM_RETRY_DELAY", "2"))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
        self.concurrency = int(os.getenv("GRAPH_CONCURRENCY", "10"))

        # Validate configuration
        if not self.llm_endpoint or not self.llm_endpoint.startswith("http"):
            raise ValueError(f"Invalid OLLAMA_LLM_ENDPOINT: {self.llm_endpoint}")
        if not self.model:
            raise ValueError("OLLAMA_LLM_MODEL cannot be empty")
        if self.timeout <= 0 or self.timeout > 600:
            raise ValueError(f"LLM_TIMEOUT must be between 0 and 600, got {self.timeout}")
        if self.concurrency < 1 or self.concurrency > 64:
            raise ValueError(f"GRAPH_CONCURRENCY must be between 1 and 64, got {self.concurrency}")

        logger.info(
            f"GraphExtractor initialized: endpoint={self.llm_endpoint}, model={self.model}, "
            f"timeout={self.timeout}s, concurrency={self.concurrency}"
        )

    def _extract_json_from_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse JSON from LLM response, handling various formats.

        Args:
            content: Raw content from LLM response

        Returns:
            Parsed JSON dict or None if parsing fails

        Note:
            Handles multiple formats:
            - Direct JSON
            - JSON in markdown code blocks (```json ... ```)
            - JSON in generic code blocks (``` ... ```)
        """
        if not content or not content.strip():
            return None

        # Strip Qwen3 thinking blocks if /no_think was not honoured
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        # Try direct JSON parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        patterns = [
            r'```json\s*\n(.*?)\n```',  # ```json ... ```
            r'```\s*\n(.*?)\n```',       # ``` ... ```
            r'{.*}',                      # Any JSON object
        ]

        for pattern in patterns:
            try:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    json_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
                    return json.loads(json_str.strip())
            except (json.JSONDecodeError, AttributeError):
                continue

        # Log failure for diagnosing any remaining edge cases
        logger.warning(f"Failed to parse JSON from LLM response. Preview: {content[:300]!r}")
        return None

    def _validate_graph_data(self, graph_data: Dict[str, Any]) -> Tuple[List[dict], List[dict]]:
        """
        Validate and extract nodes and edges from graph data.

        Args:
            graph_data: Parsed JSON containing nodes and edges

        Returns:
            Tuple of (nodes_list, edges_list)

        Note:
            Returns empty lists if structure is invalid.
        """
        if not isinstance(graph_data, dict):
            logger.warning(f"Invalid graph data type: {type(graph_data)}")
            return [], []

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        # Validate nodes structure
        if not isinstance(nodes, list):
            logger.warning(f"Invalid nodes type: {type(nodes)}")
            nodes = []

        # Validate edges structure
        if not isinstance(edges, list):
            logger.warning(f"Invalid edges type: {type(edges)}")
            edges = []

        return nodes, edges

    async def _extract_one(
        self,
        client: httpx.AsyncClient,
        text: str,
        idx: int,
        semaphore: asyncio.Semaphore,
    ) -> Tuple[int, List[dict], List[dict]]:
        """
        Extract graph data from a single text chunk with retry logic.

        Runs concurrently with other chunks via asyncio.gather. The semaphore
        caps in-flight requests to GRAPH_CONCURRENCY to avoid overloading Ollama.

        Args:
            client: Shared async HTTP client for the batch.
            text: Text chunk to extract from.
            idx: Chunk index (preserved for result ordering).
            semaphore: Bounds the number of simultaneous requests.

        Returns:
            (idx, nodes, edges) — nodes/edges are empty lists on failure.
        """
        if not text or not isinstance(text, str):
            logger.warning(f"Skipping invalid text at index {idx}: {type(text)}")
            return idx, [], []

        last_error = None
        truncated_text = text[:4000]
        # /no_think disables Qwen3 chain-of-thought (<think> blocks)
        prompt = f"""/no_think

{GraphSchema.get_system_prompt()}

Input Text:
{truncated_text}"""

        payload = {
            "model": self.model,
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a knowledge graph extraction assistant for legal documents. Extract entities and relationships from the given text and return ONLY valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            # Constrained decoding: guarantees nodes/edges structure even for
            # short or non-legal chunks that would otherwise return plain text.
            "format": GRAPH_OUTPUT_SCHEMA,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        async with semaphore:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(self.llm_endpoint, json=payload)
                    response.raise_for_status()

                    response_data = response.json()
                    content = response_data.get("message", {}).get("content", "")

                    # Detect token limit truncation — retrying produces the same result
                    if response_data.get("done_reason") == "length":
                        logger.error(
                            f"LLM truncated response for text {idx} due to token limit "
                            f"(num_predict={self.max_tokens}). Increase LLM_MAX_TOKENS."
                        )
                        return idx, [], []

                    if not content or not content.strip():
                        logger.warning(
                            f"Empty LLM response for text {idx} "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        return idx, [], []

                    graph_data = self._extract_json_from_response(content)
                    if graph_data is None:
                        raise ValueError("Failed to parse JSON from LLM response")

                    nodes, edges = self._validate_graph_data(graph_data)
                    return idx, nodes, edges

                except httpx.TimeoutException as e:
                    last_error = e
                    logger.warning(
                        f"LLM timeout for text {idx} (attempt {attempt + 1}/{self.max_retries})"
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** attempt))

                except httpx.HTTPStatusError as e:
                    last_error = e
                    logger.warning(
                        f"HTTP error for text {idx} (attempt {attempt + 1}/{self.max_retries}): "
                        f"{e.response.status_code}"
                    )
                    if e.response.status_code < 500:
                        break  # Client error — don't retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** attempt))

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Graph extraction failed for text {idx} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** attempt))

        logger.error(
            f"Failed to extract graph for text {idx} after {self.max_retries} attempts: {last_error}"
        )
        return idx, [], []

    async def _extract_all(
        self, texts: List[str]
    ) -> List[Tuple[int, List[dict], List[dict]]]:
        """
        Fire all LLM extraction requests concurrently and return results in input order.

        Batch latency is bounded by the slowest single chunk, not the sum of all chunks.
        A semaphore caps simultaneous in-flight requests to self.concurrency.
        """
        semaphore = asyncio.Semaphore(self.concurrency)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [
                self._extract_one(client, text, idx, semaphore)
                for idx, text in enumerate(texts)
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

    def __call__(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract graph data from a batch of text chunks (concurrently).

        All chunks in the batch are sent to the LLM simultaneously (bounded by
        GRAPH_CONCURRENCY), so batch latency is O(1) rather than O(n) serial
        round-trips.

        Args:
            batch: Dictionary containing:
                - "text": List[str] - Text chunks to process
                - "metadata": List[dict] - Optional metadata for each chunk

        Returns:
            Dictionary containing:
                - All input fields (text, metadata, etc.)
                - "graph_nodes": List[List[dict]] - Extracted nodes per chunk
                - "graph_edges": List[List[dict]] - Extracted edges per chunk

        Raises:
            ValueError: If batch structure is invalid.
        """
        if "text" not in batch:
            raise ValueError("Batch must contain 'text' field")

        texts = batch["text"]
        if not isinstance(texts, list):
            raise ValueError(f"Batch 'text' must be a list, got {type(texts)}")

        if not texts:
            logger.warning("Empty text list provided, returning empty graph data")
            batch["graph_nodes"] = []
            batch["graph_edges"] = []
            return batch

        raw_results = asyncio.run(self._extract_all(texts))

        # Re-order by idx to guarantee output matches input order
        nodes_list: List[List[dict]] = [[] for _ in texts]
        edges_list: List[List[dict]] = [[] for _ in texts]

        for result in raw_results:
            if isinstance(result, Exception):
                logger.error(f"Unexpected exception in graph extraction task: {result}")
                # slot already initialised to [] above — nothing to do
                continue
            idx, nodes, edges = result
            nodes_list[idx] = nodes
            edges_list[idx] = edges

        batch["graph_nodes"] = nodes_list
        batch["graph_edges"] = edges_list
        return batch

    def close(self) -> None:
        """No-op — async implementation uses per-call clients with context managers."""
        logger.debug("GraphExtractor close() called")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False
