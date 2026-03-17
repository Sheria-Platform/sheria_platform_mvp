"""Abstract async base crawler with retry, robots.txt checking, and MinIO upload."""

import asyncio
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

from scraper.config.settings import Settings
from scraper.parsers.document_parser import (
    DocumentMetadata,
    build_minio_path,
)
from scraper.storage.minio_client import MinIOClient
from scraper.utils.rate_limiter import RateLimiterRegistry

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubled each attempt
_DEFAULT_UA = "SheriaBot/1.0 (+https://sheriaplatform.go.ke/bot)"


@dataclass
class CrawlReport:
    total_urls_visited: int = 0
    documents_downloaded: int = 0
    documents_skipped_duplicate: int = 0
    documents_skipped_invalid: int = 0
    documents_failed: int = 0
    upload_failures: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class AuthenticationError(Exception):
    """Raised when the remote server returns a 401/403 response."""


class BaseCrawler(ABC):
    """
    Async base crawler that handles:
    - Session management (aiohttp with connection pooling)
    - Rate limiting (per-domain token bucket)
    - robots.txt compliance
    - Retry with exponential backoff
    - MinIO upload with local temp-dir fallback
    """

    def __init__(
        self,
        site_config: dict,
        settings: Settings,
        minio_client: MinIOClient,
    ) -> None:
        self.site_config = site_config
        self.settings = settings
        self.minio = minio_client
        self._robots_cache: Dict[str, RobotFileParser] = {}
        self._seen_hashes: set = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def crawl(self, start_urls: List[str], depth: int = 1) -> CrawlReport:
        """Entry point: crawl `start_urls` up to `depth` link levels deep."""
        connector = aiohttp.TCPConnector(limit=10)
        headers = {"User-Agent": _DEFAULT_UA}
        timeout = aiohttp.ClientTimeout(total=60)
        report = CrawlReport()

        async with aiohttp.ClientSession(
            connector=connector, headers=headers, timeout=timeout
        ) as session:
            await self._crawl_recursive(start_urls, depth, session, report)

        return report

    # ------------------------------------------------------------------
    # Internal crawl loop
    # ------------------------------------------------------------------

    async def _crawl_recursive(
        self,
        urls: List[str],
        remaining_depth: int,
        session: aiohttp.ClientSession,
        report: CrawlReport,
    ) -> None:
        sem = asyncio.Semaphore(self.settings.max_concurrent_downloads)

        async def _process(url: str) -> None:
            if not self._check_robots(url, session):
                logger.info("robots.txt blocked: %s", url)
                return
            async with sem:
                await self._process_url(url, session, report)

        await asyncio.gather(*[_process(u) for u in urls], return_exceptions=True)

        if remaining_depth > 1:
            next_links: List[str] = []
            for url in urls:
                try:
                    resp = await self._fetch(url, session)
                    if resp is not None:
                        links = await self._extract_links(resp, url)
                        next_links.extend(links)
                except Exception as exc:
                    logger.warning("Link extraction failed for %s: %s", url, exc)
            if next_links:
                await self._crawl_recursive(
                    next_links, remaining_depth - 1, session, report
                )

    async def _process_url(
        self,
        url: str,
        session: aiohttp.ClientSession,
        report: CrawlReport,
    ) -> None:
        report.total_urls_visited += 1
        try:
            content, filename = await self._download_file(url, session)
            if content is None:
                report.documents_failed += 1
                return

            meta = await self._build_metadata(url, content, filename)
            if meta is None:
                report.documents_skipped_invalid += 1
                return

            # Duplicate check (in-memory set across the session)
            if meta.sha256 in self._seen_hashes:
                logger.debug("Duplicate skipped: %s", url)
                report.documents_skipped_duplicate += 1
                return

            minio_path = build_minio_path(meta, filename)

            # MinIO-level duplicate check
            if self.minio.document_exists(minio_path):
                logger.debug("Already in MinIO, skipping: %s", minio_path)
                report.documents_skipped_duplicate += 1
                self._seen_hashes.add(meta.sha256)
                return

            await self._upload(content, minio_path, meta, report)
            self._seen_hashes.add(meta.sha256)
            report.documents_downloaded += 1

        except AuthenticationError as exc:
            logger.error("Auth failure for %s: %s", url, exc)
            raise
        except Exception as exc:
            logger.warning("Failed to process %s: %s", url, exc)
            report.documents_failed += 1
            report.errors.append(f"{url}: {exc}")

    # ------------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------------

    async def _fetch(
        self, url: str, session: aiohttp.ClientSession
    ) -> Optional[aiohttp.ClientResponse]:
        """GET `url` with retry + rate limiting. Returns response or None."""
        domain = urlparse(url).netloc
        rps = self.site_config.get(
            "rate_limit_rps", self.settings.default_rate_limit_rps
        )
        limiter = RateLimiterRegistry.get(domain, rps)

        for attempt in range(_MAX_RETRIES):
            async with limiter:
                try:
                    resp = await session.get(url, allow_redirects=True)
                    if resp.status == 401 or resp.status == 403:
                        raise AuthenticationError(f"HTTP {resp.status} from {url}")
                    resp.raise_for_status()
                    return resp
                except AuthenticationError:
                    raise
                except aiohttp.ClientResponseError as exc:
                    if exc.status in (429, 503) or attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_BASE_DELAY * (2**attempt)
                        logger.warning(
                            "Attempt %d/%d failed for %s (status %d). Retrying in %.1fs.",
                            attempt + 1,
                            _MAX_RETRIES,
                            url,
                            exc.status,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Attempt %d/%d network error for %s: %s. Retrying in %.1fs.",
                        attempt + 1,
                        _MAX_RETRIES,
                        url,
                        exc,
                        delay,
                    )
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                    else:
                        return None
        return None

    async def _download_file(
        self, url: str, session: aiohttp.ClientSession
    ) -> Tuple[Optional[bytes], str]:
        """Download file bytes and derive a safe filename. Returns (content, filename)."""
        resp = await self._fetch(url, session)
        if resp is None:
            return None, ""
        content = await resp.read()
        filename = url.rstrip("/").split("/")[-1] or "document"
        if "." not in filename:
            filename += ".pdf"
        return content, filename

    # ------------------------------------------------------------------
    # Upload with local fallback
    # ------------------------------------------------------------------

    async def _upload(
        self,
        content: bytes,
        minio_path: str,
        meta: DocumentMetadata,
        report: CrawlReport,
    ) -> None:
        from scraper.parsers.document_parser import build_metadata_json
        from scraper.utils.validators import detect_mime_type

        content_type = detect_mime_type(content, minio_path)
        try:
            self.minio.upload_document(
                content,
                minio_path,
                metadata={"sha256": meta.sha256, "source": meta.source},
                content_type=content_type,
            )
            self.minio.upload_metadata_json(build_metadata_json(meta), minio_path)
        except Exception as exc:
            logger.warning(
                "MinIO upload failed for %s: %s. Falling back to local temp dir.",
                minio_path,
                exc,
            )
            report.upload_failures.append(minio_path)
            self._save_local_fallback(content, minio_path)

    def _save_local_fallback(self, content: bytes, minio_path: str) -> None:
        """Write content to a local temp directory when MinIO is unavailable."""
        temp_dir = os.path.join(tempfile.gettempdir(), "sheria_scraper_temp")
        local_path = os.path.join(temp_dir, minio_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as fh:
            fh.write(content)
        logger.info("Saved locally (fallback): %s", local_path)

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    def _check_robots(
        self, url: str, session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Return True if the URL is allowed by robots.txt (synchronous check via cache)."""
        if not self.site_config.get("robots_txt", True):
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            robots_url = f"{origin}/robots.txt"
            rp = RobotFileParser(robots_url)
            try:
                rp.read()
            except Exception:
                # If robots.txt is unreachable, allow crawling
                rp.allow_all = True
            self._robots_cache[origin] = rp
        return self._robots_cache[origin].can_fetch(_DEFAULT_UA, url)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def _extract_links(
        self, response: aiohttp.ClientResponse, base_url: str
    ) -> List[str]:
        """Extract follow-up URLs from the page response."""

    @abstractmethod
    async def _extract_metadata(
        self, response: aiohttp.ClientResponse, url: str
    ) -> DocumentMetadata:
        """Build document metadata from the response and URL."""

    async def _build_metadata(
        self, url: str, content: bytes, filename: str
    ) -> Optional[DocumentMetadata]:
        """Validate content and delegate to _extract_metadata."""
        from scraper.utils.validators import compute_sha256, validate_docx, validate_pdf

        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "pdf" and not validate_pdf(content):
            logger.warning("Invalid PDF (bad magic bytes): %s", url)
            return None
        if ext in ("docx", "doc") and not validate_docx(content):
            logger.warning("Invalid DOCX (bad magic bytes): %s", url)
            return None

        # Use a dummy response placeholder for metadata extraction
        meta = DocumentMetadata(
            source_url=url,
            sha256=compute_sha256(content),
            file_size=len(content),
            doc_type=ext,
        )
        return meta
