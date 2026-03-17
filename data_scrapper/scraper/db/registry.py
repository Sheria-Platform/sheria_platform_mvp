"""
Thread-safe PostgreSQL document registry using psycopg2 connection pooling.

Tracks scraped documents and ingestion run history to enable:
- O(1) deduplication across process restarts (pre-loaded sets)
- Ingestion run auditing (start time, status, doc count, stats)
- Cross-run analytics (which documents are ingested vs scraped-only)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)

_CREATE_INGESTION_RUNS = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    doc_count       INTEGER NOT NULL DEFAULT 0,
    stats           JSONB,
    error_message   TEXT
);
"""

_CREATE_SCRAPER_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS scraper_documents (
    id               SERIAL PRIMARY KEY,
    minio_path       TEXT UNIQUE NOT NULL,
    sha256           TEXT NOT NULL,
    court            TEXT,
    year             TEXT,
    title            TEXT,
    source_url       TEXT NOT NULL,
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_at      TIMESTAMPTZ,
    ingestion_run_id INTEGER REFERENCES ingestion_runs(id) ON DELETE SET NULL
);
"""

_CREATE_INDEX_SHA256 = """
CREATE INDEX IF NOT EXISTS ix_scraper_documents_sha256
    ON scraper_documents (sha256);
"""


class DocumentRegistry:
    """
    Thread-safe PostgreSQL registry for scraped documents and ingestion runs.

    Usage::

        registry = DocumentRegistry(database_url)
        registry.ensure_tables()
        known_paths = registry.load_known_paths()   # pre-load at startup
        known_hashes = registry.load_known_hashes()

        doc_id = registry.mark_scraped(minio_path, sha256, source_url)
        run_id = registry.create_run(doc_count=5)
        registry.complete_run(run_id, stats={"vectors_indexed": 5})
        registry.mark_ingested([minio_path], ingestion_run_id=run_id)

        registry.close()
    """

    _POOL_MIN = 1
    _POOL_MAX = 4

    def __init__(self, database_url: str) -> None:
        self._pool = pg_pool.ThreadedConnectionPool(
            self._POOL_MIN,
            self._POOL_MAX,
            dsn=database_url,
        )
        logger.debug("DocumentRegistry: connection pool created (min=%d, max=%d)",
                     self._POOL_MIN, self._POOL_MAX)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def ensure_tables(self) -> None:
        """Create tables and indexes if they do not already exist."""
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_INGESTION_RUNS)
                    cur.execute(_CREATE_SCRAPER_DOCUMENTS)
                    cur.execute(_CREATE_INDEX_SHA256)
            logger.info("DocumentRegistry: tables verified/created")
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Bulk pre-load (call once at startup for O(1) per-document checks)
    # ------------------------------------------------------------------

    def load_known_paths(self) -> set:
        """Return the set of all minio_path values in scraper_documents."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT minio_path FROM scraper_documents")
                paths = {row[0] for row in cur.fetchall()}
            logger.info("DocumentRegistry: loaded %d known paths", len(paths))
            return paths
        finally:
            self._pool.putconn(conn)

    def load_known_hashes(self) -> set:
        """Return the set of all sha256 values in scraper_documents."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT sha256 FROM scraper_documents")
                hashes = {row[0] for row in cur.fetchall()}
            logger.info("DocumentRegistry: loaded %d known hashes", len(hashes))
            return hashes
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Document writes
    # ------------------------------------------------------------------

    def mark_scraped(
        self,
        minio_path: str,
        sha256: str,
        source_url: str,
        court: Optional[str] = None,
        year: Optional[str] = None,
        title: Optional[str] = None,
    ) -> int:
        """
        Insert a new document record.

        Uses ON CONFLICT DO NOTHING so concurrent/duplicate calls are safe.
        Returns the row id (0 if nothing was inserted due to conflict).
        """
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scraper_documents
                            (minio_path, sha256, source_url, court, year, title)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (minio_path) DO NOTHING
                        RETURNING id
                        """,
                        (minio_path, sha256, source_url, court, year, title),
                    )
                    row = cur.fetchone()
                    return row[0] if row else 0
        finally:
            self._pool.putconn(conn)

    def mark_ingested(
        self,
        minio_paths: list,
        ingestion_run_id: int,
        ingested_at: Optional[datetime] = None,
    ) -> int:
        """
        Mark a list of documents as ingested.

        Returns the number of rows updated.
        """
        if not minio_paths:
            return 0
        ts = ingested_at or datetime.now(tz=timezone.utc)
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE scraper_documents
                           SET ingested_at = %s,
                               ingestion_run_id = %s
                         WHERE minio_path = ANY(%s)
                        """,
                        (ts, ingestion_run_id, minio_paths),
                    )
                    return cur.rowcount
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Ingestion run lifecycle
    # ------------------------------------------------------------------

    def create_run(self, doc_count: int) -> int:
        """Insert a new ingestion_run record and return its id."""
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO ingestion_runs (doc_count)
                        VALUES (%s)
                        RETURNING id
                        """,
                        (doc_count,),
                    )
                    run_id = cur.fetchone()[0]
            logger.debug("DocumentRegistry: created ingestion run %d (%d docs)", run_id, doc_count)
            return run_id
        finally:
            self._pool.putconn(conn)

    def complete_run(self, run_id: int, stats: dict) -> None:
        """Mark an ingestion run as completed with final statistics."""
        import json
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE ingestion_runs
                           SET status = 'completed',
                               completed_at = NOW(),
                               stats = %s
                         WHERE id = %s
                        """,
                        (json.dumps(stats), run_id),
                    )
            logger.info("DocumentRegistry: run %d completed — %s", run_id, stats)
        finally:
            self._pool.putconn(conn)

    def fail_run(self, run_id: int, error_message: str) -> None:
        """Mark an ingestion run as failed with an error message."""
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE ingestion_runs
                           SET status = 'failed',
                               completed_at = NOW(),
                               error_message = %s
                         WHERE id = %s
                        """,
                        (error_message, run_id),
                    )
            logger.warning("DocumentRegistry: run %d failed — %s", run_id, error_message)
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()
        logger.debug("DocumentRegistry: connection pool closed")
