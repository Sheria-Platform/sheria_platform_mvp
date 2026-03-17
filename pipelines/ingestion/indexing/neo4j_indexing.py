# pipelines/ingestion/indexing/neo4j_indexing.py
"""
Neo4j graph database indexing module for Sheria Platform.

This module provides the Neo4jIndexer class which writes legal entities and
relationships to Neo4j for citation graph queries. It includes retry logic,
idempotent writes, and proper error handling.

Environment Variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (default: changeme)
    NEO4J_TIMEOUT: Connection timeout in seconds (default: 30)
    NEO4J_MAX_RETRIES: Maximum retry attempts (default: 3)
"""

import logging
import os
import time
from collections import defaultdict
from typing import Any

from pipelines.ingestion.graph.schema_graph import (
    VALID_RELATION_TYPES as _SCHEMA_RELATION_TYPES,
)

VALID_RELATION_TYPES = frozenset(_SCHEMA_RELATION_TYPES.__args__)

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, TransientError

logger = logging.getLogger(__name__)


class Neo4jIndexer:
    """
    Index legal entities and relationships to Neo4j graph database.

    This class handles batch writes of graph nodes (entities) and edges
    (relationships) extracted from legal documents. Uses idempotent MERGE
    operations to prevent duplicate entries.

    Features:
        - Idempotent writes (MERGE instead of CREATE)
        - Automatic retry with exponential backoff
        - Batch validation
        - Transaction management
        - Proper error logging
        - Resource cleanup

    Attributes:
        driver: Neo4j driver instance
        timeout (int): Connection timeout in seconds
        max_retries (int): Maximum retry attempts

    Example:
        >>> indexer = Neo4jIndexer()
        >>> chunks = [{"graph_nodes": [...], "graph_edges": [...]}]
        >>> indexer.write(chunks)
        >>> indexer.close()
    """

    def __init__(self):
        """
        Initialize Neo4jIndexer with configuration from environment variables.

        Raises:
            ValueError: If configuration is invalid
            Exception: If connection to Neo4j fails
        """
        # Load configuration
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "changeme")
        self.timeout = int(os.getenv("NEO4J_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("NEO4J_MAX_RETRIES", "3"))

        # Validate configuration
        if not uri or not uri.startswith("bolt://"):
            raise ValueError(f"Invalid NEO4J_URI: {uri}")
        if not user:
            raise ValueError("NEO4J_USER cannot be empty")
        if not password or password == "changeme":
            logger.warning(
                "Using default Neo4j password 'changeme' - not recommended for production"
            )

        # Initialize driver
        try:
            self.driver = GraphDatabase.driver(
                uri, auth=(user, password), connection_timeout=self.timeout
            )

            # Test connection
            self.driver.verify_connectivity()
            logger.info(f"Neo4jIndexer initialized: uri={uri}, user={user}")

        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def _validate_graph_data(
        self, batch: list[dict[str, Any]]
    ) -> tuple[list[dict], list[dict]]:
        """
        Validate and extract nodes and edges from batch.

        Args:
            batch: List of chunks containing graph_nodes and graph_edges

        Returns:
            Tuple of (all_nodes, all_edges) lists
        """
        all_nodes = []
        all_edges = []

        for idx, row in enumerate(batch):
            if not isinstance(row, dict):
                logger.warning(f"Skipping invalid row at index {idx}: not a dict")
                continue

            # Extract nodes
            if "graph_nodes" in row:
                nodes = row["graph_nodes"]
                if isinstance(nodes, list):
                    # Validate each node has required fields
                    for node in nodes:
                        if isinstance(node, dict) and "id" in node and "type" in node:
                            all_nodes.append(node)
                        else:
                            logger.debug(f"Skipping invalid node: {node}")

            # Extract edges
            if "graph_edges" in row:
                edges = row["graph_edges"]
                if isinstance(edges, list):
                    # Validate each edge has required fields
                    for edge in edges:
                        if isinstance(edge, dict) and all(
                            k in edge for k in ["source", "target", "type"]
                        ):
                            all_edges.append(edge)
                        else:
                            logger.debug(f"Skipping invalid edge: {edge}")

        return all_nodes, all_edges

    def write(self, batch: list[dict[str, Any]], max_retries: int = None) -> int:
        """
        Write graph data to Neo4j in batch with retry logic.

        Args:
            batch: List of dictionaries containing:
                - "graph_nodes": List[dict] - Entities (id, type)
                - "graph_edges": List[dict] - Relationships (source, target, type)
            max_retries: Maximum retry attempts (overrides default)

        Returns:
            Number of entities successfully indexed (approximate)

        Raises:
            ValueError: If batch is invalid
            Exception: If all retry attempts fail

        Note:
            Uses MERGE operations for idempotency - repeated writes are safe.
        """
        if not batch:
            logger.warning("Empty batch provided")
            return 0

        if not isinstance(batch, list):
            raise ValueError(f"Batch must be a list, got {type(batch)}")

        # Validate and extract graph data
        all_nodes, all_edges = self._validate_graph_data(batch)

        if not all_nodes and not all_edges:
            logger.debug("No valid graph data in batch")
            return 0

        logger.debug(
            f"Writing {len(all_nodes)} nodes and {len(all_edges)} edges to Neo4j"
        )

        retries = max_retries if max_retries is not None else self.max_retries

        # Retry loop
        for attempt in range(retries):
            try:
                with self.driver.session() as session:
                    session.execute_write(self._merge_graph_data, all_nodes, all_edges)

                logger.debug(f"Successfully wrote graph data to Neo4j")
                return len(all_nodes)

            except TransientError as e:
                logger.warning(
                    f"Neo4j transient error (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(1 * (2**attempt))  # Exponential backoff
                else:
                    logger.error(f"Failed to write graph data after {retries} attempts")
                    raise

            except ServiceUnavailable as e:
                logger.error(
                    f"Neo4j service unavailable (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(2 * (2**attempt))
                else:
                    raise

            except Exception as e:
                logger.error(
                    f"Unexpected error during Neo4j write (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(1 * (2**attempt))
                else:
                    raise

        return 0

    @staticmethod
    def _merge_graph_data(tx, nodes, edges):
        """
        Execute Cypher queries to merge graph data idempotently.

        Args:
            tx: Neo4j transaction
            nodes: List of node dictionaries (id, type)
            edges: List of edge dictionaries (source, target, type)

        Note:
            Uses MERGE to create nodes/edges only if they don't exist.
            This makes the operation idempotent and safe for retries.
        """
        # 1. Merge Nodes
        if nodes:
            # UNWIND expands the list $nodes into individual rows
            # MERGE creates node only if it doesn't exist
            cypher_nodes = """
            UNWIND $nodes AS n
            MERGE (node:Entity {name: n.id})
            SET node.type = n.type,
                node.updated_at = timestamp()
            """
            try:
                result = tx.run(cypher_nodes, nodes=nodes)
                result.consume()  # Ensure query completes
            except Exception as e:
                logger.error(f"Failed to merge nodes: {e}")
                raise

        # 2. Merge Edges — one Cypher per relationship type for native index use
        if edges:
            by_type = defaultdict(list)
            for e in edges:
                rel_type = e.get("type", "").upper()
                if rel_type in VALID_RELATION_TYPES:
                    by_type[rel_type].append(e)
                else:
                    logger.warning(
                        f"Skipping edge with unknown relationship type: {rel_type!r}"
                    )

            for rel_type, typed_edges in by_type.items():
                cypher = f"""
                UNWIND $edges AS e
                MATCH (source:Entity {{name: e.source}})
                MATCH (target:Entity {{name: e.target}})
                MERGE (source)-[r:{rel_type}]->(target)
                SET r.updated_at = timestamp()
                """
                try:
                    result = tx.run(cypher, edges=typed_edges)
                    result.consume()
                except Exception as e:
                    logger.warning(
                        f"Failed to merge {rel_type} edges (may be missing nodes): {e}"
                    )
                    # Don't raise - some edges may reference nodes that don't exist

    def close(self) -> None:
        """
        Clean up resources (close Neo4j driver).

        Should be called when the indexer is no longer needed.
        """
        try:
            self.driver.close()
            logger.debug("Neo4jIndexer driver closed")
        except Exception as e:
            logger.warning(f"Error closing Neo4j driver: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False
