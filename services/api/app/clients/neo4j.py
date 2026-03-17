# services/api/app/clients/neo4j.py
"""Async Neo4j graph database client.

Provides a singleton wrapper around the ``neo4j`` async driver.
Lifecycle (``connect`` / ``close``) is managed by the FastAPI
lifespan handler in ``services/api/main.py``.

Example:
    >>> await neo4j_client.query(
    ...     "MATCH (n:Case) RETURN n.name LIMIT 5"
    ... )
"""

import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from services.api.app.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Singleton async wrapper for the Neo4j driver.

    Manages a single connection pool shared across all FastAPI request
    handlers.  The driver is initialised in ``connect()`` and torn down
    in ``close()``, both called from the application lifespan context.

    Attributes:
        _driver: The underlying ``neo4j.AsyncDriver`` instance, or
            ``None`` before ``connect()`` is called.
    """

    def __init__(self) -> None:
        """Initialise with no active driver."""
        self._driver = None

    def connect(self) -> None:
        """Open the Neo4j connection pool.

        Idempotent — calling it more than once has no effect.

        Raises:
            neo4j.exceptions.ServiceUnavailable: If the Neo4j server
                cannot be reached at the configured URI.
            Exception: For any other driver initialisation error.
        """
        if self._driver:
            return

        try:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            logger.info("Neo4j driver initialised. uri=%s", settings.NEO4J_URI)
        except Exception as exc:
            logger.error("Failed to initialise Neo4j driver: %s", exc)
            raise

    async def close(self) -> None:
        """Close the Neo4j connection pool.

        Safe to call even if ``connect()`` was never called.
        """
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j driver closed.")

    async def query(
        self,
        cypher_query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher read query and return all rows.

        Args:
            cypher_query: A valid Cypher query string.
            parameters: Optional mapping of parameter names to values
                (use parameterised queries to prevent injection).

        Returns:
            A list of row dictionaries, one per record returned by
            the database.

        Raises:
            RuntimeError: If called before ``connect()``.
            neo4j.exceptions.CypherSyntaxError: On malformed Cypher.

        Example:
            >>> rows = await neo4j_client.query(
            ...     "MATCH (c:Case {id: $id}) RETURN c",
            ...     {"id": "2023-SC-001"},
            ... )
        """
        if not self._driver:
            raise RuntimeError("Neo4jClient not connected. Call connect() first.")

        async with self._driver.session() as session:
            result = await session.run(cypher_query, parameters or {})
            return [record.data() async for record in result]


# Global singleton — lifecycle managed by main.py lifespan
neo4j_client = Neo4jClient()
