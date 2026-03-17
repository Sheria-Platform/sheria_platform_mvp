# pipelines/ingestion/indexing/qdrant_indexing.py
"""
Qdrant vector database indexing module for Sheria Platform.

This module provides the QdrantIndexer class which writes vector embeddings
to Qdrant for semantic search. It includes retry logic, batch validation,
and proper error handling.

Environment Variables:
    QDRANT_HOST: Qdrant server host (default: localhost)
    QDRANT_PORT: Qdrant server port (default: 6333)
    QDRANT_COLLECTION: Collection name (default: kenya_law_reports)
    QDRANT_TIMEOUT: Request timeout in seconds (default: 60)
    QDRANT_MAX_RETRIES: Maximum retry attempts (default: 3)
"""

import logging
import os
import time
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)


class QdrantIndexer:
    """
    Index vector embeddings to Qdrant for semantic search.

    This class handles batch upserts of document chunks with their vector
    embeddings to Qdrant. It includes automatic retry logic and validation.

    Features:
        - Automatic retry with exponential backoff
        - Batch validation (skip invalid vectors)
        - UUID generation for unique point IDs
        - Proper error logging
        - Resource cleanup

    Attributes:
        client (QdrantClient): Qdrant database client
        collection_name (str): Target collection name
        timeout (int): Request timeout in seconds
        max_retries (int): Maximum retry attempts

    Example:
        >>> indexer = QdrantIndexer()
        >>> chunks = [{"text": "...", "vector": [...], "metadata": {...}}]
        >>> indexer.write(chunks)
        >>> indexer.close()
    """

    def __init__(self):
        """
        Initialize QdrantIndexer with configuration from environment variables.

        Raises:
            ValueError: If configuration is invalid
            Exception: If connection to Qdrant fails
        """
        # Load configuration
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        self.collection_name = os.getenv("QDRANT_COLLECTION", "kenya_law_reports")
        self.timeout = int(os.getenv("QDRANT_TIMEOUT", "60"))
        self.max_retries = int(os.getenv("QDRANT_MAX_RETRIES", "3"))

        # Validate configuration
        if not host:
            raise ValueError("QDRANT_HOST cannot be empty")
        if port <= 0 or port > 65535:
            raise ValueError(f"Invalid QDRANT_PORT: {port}")
        if not self.collection_name:
            raise ValueError("QDRANT_COLLECTION cannot be empty")

        # Initialize client
        try:
            self.client = QdrantClient(host=host, port=port, timeout=self.timeout)
            logger.info(
                f"QdrantIndexer initialized: host={host}:{port}, collection={self.collection_name}"
            )

            # Verify collection exists
            try:
                self.client.get_collection(collection_name=self.collection_name)
            except Exception as e:
                logger.warning(
                    f"Collection '{self.collection_name}' may not exist: {e}"
                )

        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    def _validate_vector(self, vector: Any, expected_dim: int = None) -> bool:
        """
        Validate vector structure and dimensions.

        Args:
            vector: Vector to validate
            expected_dim: Expected vector dimension (optional)

        Returns:
            True if valid, False otherwise
        """
        if not vector:
            return False

        if not isinstance(vector, list):
            logger.warning(f"Invalid vector type: {type(vector)}")
            return False

        if not all(isinstance(x, (int, float)) for x in vector):
            logger.warning("Vector contains non-numeric values")
            return False

        if expected_dim and len(vector) != expected_dim:
            logger.warning(
                f"Vector dimension mismatch: expected {expected_dim}, got {len(vector)}"
            )
            return False

        return True

    def write(self, batch: list[dict[str, Any]], max_retries: int = None) -> int:
        """
        Upload vector points to Qdrant in batch with retry logic.

        Args:
            batch: List of dictionaries containing:
                - "text": str - Document text
                - "vector": List[float] - Embedding vector
                - "metadata": dict - Document metadata
            max_retries: Maximum retry attempts (overrides default)

        Returns:
            Number of points successfully indexed

        Raises:
            ValueError: If batch is invalid
            Exception: If all retry attempts fail

        Note:
            Invalid vectors are skipped rather than failing the entire batch.
        """
        if not batch:
            logger.warning("Empty batch provided")
            return 0

        if not isinstance(batch, list):
            raise ValueError(f"Batch must be a list, got {type(batch)}")

        retries = max_retries if max_retries is not None else self.max_retries
        points = []
        skipped = 0

        # Build points list
        for idx, row in enumerate(batch):
            try:
                # Validate required fields
                if not isinstance(row, dict):
                    logger.warning(f"Skipping invalid row at index {idx}: not a dict")
                    skipped += 1
                    continue

                # Skip if embedding failed or is invalid
                if "vector" not in row or not self._validate_vector(row.get("vector")):
                    logger.debug(f"Skipping row {idx}: invalid or missing vector")
                    skipped += 1
                    continue

                # Validate text field
                if "text" not in row or not row["text"]:
                    logger.warning(f"Skipping row {idx}: missing text")
                    skipped += 1
                    continue

                # Construct Payload (Metadata)
                metadata = row.get("metadata", {})
                payload = {
                    "text": row["text"][:10000],  # Truncate very long text
                    "filename": metadata.get(
                        "filename", metadata.get("filepath", "unknown")
                    ),
                    "page": metadata.get("page_number", metadata.get("page", 0)),
                    "type": metadata.get("type", "unknown"),
                }

                # Add any additional metadata fields
                for key, value in metadata.items():
                    if key not in payload and isinstance(
                        value, (str, int, float, bool)
                    ):
                        payload[key] = value

                # Create Point
                points.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),  # Generate unique ID for the vector
                        vector=row["vector"],
                        payload=payload,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to process row {idx}: {e}")
                skipped += 1

        if not points:
            logger.warning(f"No valid points in batch (skipped {skipped}/{len(batch)})")
            return 0

        # Upsert with retry logic
        for attempt in range(retries):
            try:
                self.client.upsert(
                    collection_name=self.collection_name, points=points, wait=False
                )
                logger.debug(f"Successfully indexed {len(points)} points to Qdrant")
                return len(points)

            except UnexpectedResponse as e:
                logger.warning(
                    f"Qdrant upsert failed (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(1 * (2**attempt))  # Exponential backoff
                else:
                    logger.error(f"Failed to upsert after {retries} attempts")
                    raise

            except Exception as e:
                logger.error(
                    f"Unexpected error during upsert (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(1 * (2**attempt))
                else:
                    raise

        return 0

    def close(self) -> None:
        """
        Clean up resources (close Qdrant client).

        Should be called when the indexer is no longer needed.
        """
        try:
            self.client.close()
            logger.debug("QdrantIndexer client closed")
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False


# from qdrant_client import QdrantClient
# from qdrant_client.http import models

# client = QdrantClient(host="192.168.214.21", port=6333)

# # Drop old collection (2560-dim)
# client.delete_collection("kenya_law_reports")

# # Recreate with nomic-embed-text dimensions (768-dim)
# client.create_collection(
#     collection_name="kenya_law_reports",
#     vectors_config=models.VectorParams(
#         size=768,
#         distance=models.Distance.COSINE
#     )
# )
# print("Collection recreated at 768 dimensions")
