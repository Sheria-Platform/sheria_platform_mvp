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
    LLM_MAX_TOKENS: Maximum tokens for generation (default: 1024)
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from pipelines.ingestion.graph.schema_graph import GraphSchema

logger = logging.getLogger(__name__)


class GraphExtractor:
    """
    Extract legal entities and relationships from text using LLM.

    This class uses Ollama's chat API to extract structured graph data (nodes
    and edges) from legal text chunks. It enforces a predefined schema and
    handles JSON parsing robustness.

    Features:
        - Automatic retry with exponential backoff
        - Robust JSON parsing (handles markdown code blocks)
        - Schema validation
        - Request timeout handling
        - Resource cleanup (HTTP client)
        - Detailed error logging

    Attributes:
        llm_endpoint (str): Ollama chat API endpoint URL
        model (str): LLM model name
        timeout (float): Request timeout in seconds
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Initial retry delay in seconds
        temperature (float): LLM temperature (0.0 for deterministic)
        max_tokens (int): Maximum tokens for generation
        client (httpx.Client): HTTP client for API requests

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
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))

        # Validate configuration
        if not self.llm_endpoint or not self.llm_endpoint.startswith("http"):
            raise ValueError(f"Invalid OLLAMA_LLM_ENDPOINT: {self.llm_endpoint}")
        if not self.model:
            raise ValueError("OLLAMA_LLM_MODEL cannot be empty")
        if self.timeout <= 0 or self.timeout > 600:
            raise ValueError(f"LLM_TIMEOUT must be between 0 and 600, got {self.timeout}")

        # Initialize HTTP client
        self.client = httpx.Client(timeout=self.timeout)

        logger.info(f"GraphExtractor initialized: endpoint={self.llm_endpoint}, model={self.model}, timeout={self.timeout}s")

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

        # Log failure for debugging
        logger.debug(f"Failed to parse JSON. Content preview: {content[:200]}")
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

    def __call__(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract graph data from a batch of text chunks.

        Uses Ollama's chat API with structured prompts to extract legal entities
        (cases, judges, statutes) and relationships (CITES, OVERRULES, etc.).

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
            ValueError: If batch structure is invalid
            Exception: For critical failures

        Note:
            Failed extractions return empty nodes/edges lists rather than failing
            the entire batch.
        """
        # Validate input
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

        nodes_list = []
        edges_list = []

        # Process each text chunk
        for idx, text in enumerate(texts):
            if not text or not isinstance(text, str):
                logger.warning(f"Skipping invalid text at index {idx}: {type(text)}")
                nodes_list.append([])
                edges_list.append([])
                continue

            # Retry loop for this text
            success = False
            last_error = None

            for attempt in range(self.max_retries):
                try:
                    # 1. Construct Prompt
                    prompt = f"""{GraphSchema.get_system_prompt()}

Input Text:
{text[:4000]}  # Truncate to avoid token limits
"""

                    # 2. Call Ollama LLM
                    response = self.client.post(
                        self.llm_endpoint,
                        json={
                            "model": self.model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a knowledge graph extraction assistant for legal documents. Extract entities and relationships from the given text and return ONLY valid JSON."
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ],
                            "stream": False,
                            "options": {
                                "temperature": self.temperature,
                                "num_predict": self.max_tokens,
                            },
                            "format": "json"  # Request JSON response format
                        },
                    )
                    response.raise_for_status()

                    # 3. Parse JSON Output
                    response_data = response.json()
                    content = response_data.get("message", {}).get("content", "")

                    if not content or not content.strip():
                        logger.warning(f"Empty response from LLM for text {idx} (attempt {attempt + 1}/{self.max_retries})")
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        else:
                            nodes_list.append([])
                            edges_list.append([])
                            break

                    # Parse JSON (with fallback handling)
                    graph_data = self._extract_json_from_response(content)

                    if graph_data is None:
                        raise ValueError("Failed to parse JSON from LLM response")

                    # Validate and extract nodes/edges
                    nodes, edges = self._validate_graph_data(graph_data)
                    nodes_list.append(nodes)
                    edges_list.append(edges)

                    success = True
                    break

                except httpx.TimeoutException as e:
                    last_error = e
                    logger.warning(f"LLM timeout for text {idx} (attempt {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))

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
                    logger.warning(f"Graph extraction failed for text {idx} (attempt {attempt + 1}/{self.max_retries}): {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))

            if not success:
                logger.error(f"Failed to extract graph for text {idx} after {self.max_retries} attempts: {last_error}")
                nodes_list.append([])
                edges_list.append([])

        # Add graph data to batch
        batch["graph_nodes"] = nodes_list
        batch["graph_edges"] = edges_list
        return batch

    def close(self) -> None:
        """
        Clean up resources (close HTTP client).

        Should be called when the extractor is no longer needed to ensure
        proper connection cleanup.
        """
        try:
            self.client.close()
            logger.debug("GraphExtractor HTTP client closed")
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False
