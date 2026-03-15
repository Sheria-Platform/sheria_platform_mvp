"""
Concrete crawlers for Kenya Law (new.kenyalaw.org) and generic legal sites.

Kenya Law site structure (discovered 2026-02-27):
  Judgment listings  : /judgments/{COURT_CODE}/?page=N
  Search results     : /search/?q={term}&page=N
  Individual document: /akn/ke/judgment/{court}/{year}/{number}/eng@{date}
  PDF download       : /akn/ke/judgment/{court}/{year}/{number}/eng@{date}/source.pdf
  DOCX download      : /akn/ke/judgment/{court}/{year}/{number}/eng@{date}/source

Court codes:
  KESC   - Supreme Court
  KECA   - Court of Appeal
  KEHC   - High Court
  KEELRC - Employment and Labour Relations Court
  KEELC  - Environment and Land Court
  KEIC   - Industrial Court

No public JSON/REST API is available. All parsing is HTML-based (BeautifulSoup).
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from scraper.config.settings import Settings
from scraper.crawlers.base import BaseCrawler, CrawlReport
from scraper.parsers.document_parser import DocumentMetadata, build_minio_path
from scraper.storage.minio_client import MinIOClient
from scraper.utils.validators import compute_sha256, validate_pdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Court catalogue
# ---------------------------------------------------------------------------

COURT_CODES: Dict[str, str] = {
    "supreme_court": "KESC",
    "court_of_appeal": "KECA",
    "high_court": "KEHC",
    "employment_labour": "KEELRC",
    "environment_land": "KEELC",
    "industrial_court": "KEIC",
}

# Human-readable names for metadata
COURT_NAMES: Dict[str, str] = {
    "KESC": "Supreme Court of Kenya",
    "KECA": "Court of Appeal of Kenya",
    "KEHC": "High Court of Kenya",
    "KEELRC": "Employment and Labour Relations Court",
    "KEELC": "Environment and Land Court",
    "KEIC": "Industrial Court of Kenya",
}

# AKN URL pattern for individual judgments
_AKN_HREF_RE = re.compile(
    r"/akn/ke/judgment/([a-z]+)/(\d{4})/(\d+)/eng@(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

# Anchor text pattern:
# "Title v Party (Case Number) [Year] COURT Num (Date) (Type)"
_ANCHOR_TEXT_RE = re.compile(
    r"^(?P<title>.+?)\s*"
    r"\((?P<case_number>[^)]+)\)\s*"
    r"\[(?P<year>\d{4})\]\s+(?P<court_code>[A-Z]+)\s+(?P<citation_num>\d+)"
    r".*?\((?P<date>[^)]+\d{4}[^)]*)\)\s*"
    r"(?:\((?P<doc_type>[^)]+)\))?",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _parse_year(text: str) -> Optional[str]:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return m.group(0) if m else None


def _parse_anchor_metadata(anchor_text: str) -> Dict[str, Optional[str]]:
    """
    Extract structured metadata from Kenya Law listing anchor text.

    Input:  "Republic v Kamau (HC CR 123/2024) [2024] KEHC 456 (15 January 2024) (Judgment)"
    Output: {title, case_number, year, court_code, citation, date, doc_type}
    """
    text = _clean_text(anchor_text)
    m = _ANCHOR_TEXT_RE.match(text)
    if not m:
        # Fallback: at least try to get the title (everything before the first bracket)
        title_match = re.match(r"^([^(\[]+)", text)
        return {
            "title": _clean_text(title_match.group(1)) if title_match else text,
            "case_number": None,
            "year": _parse_year(text),
            "court_code": None,
            "citation": None,
            "date": None,
            "doc_type": None,
        }
    court_code = m.group("court_code").upper()
    citation_num = m.group("citation_num")
    court_label = m.group("court_code")
    return {
        "title": _clean_text(m.group("title")),
        "case_number": _clean_text(m.group("case_number")),
        "year": m.group("year"),
        "court_code": court_code,
        "citation": f"[{m.group('year')}] {court_label} {citation_num}",
        "date": _clean_text(m.group("date")),
        "doc_type": _clean_text(m.group("doc_type")) if m.group("doc_type") else None,
    }


def _akn_to_pdf_url(base_url: str, akn_href: str) -> str:
    """Convert an AKN document href to its PDF download URL."""
    return urljoin(base_url, akn_href.rstrip("/") + "/source.pdf")


def _akn_to_docx_url(base_url: str, akn_href: str) -> str:
    """Convert an AKN document href to its DOCX download URL."""
    return urljoin(base_url, akn_href.rstrip("/") + "/source")


@dataclass
class JudgmentLink:
    """Parsed judgment link extracted from a listing or search page."""

    akn_href: str  # e.g. /akn/ke/judgment/kesc/2026/20/eng@2026-02-20
    pdf_url: str
    docx_url: str
    court_code: str  # e.g. KESC
    year: str
    citation_number: str
    date: str
    title: Optional[str] = None
    case_number: Optional[str] = None
    citation: Optional[str] = None
    doc_type_label: Optional[str] = None  # "Judgment" / "Ruling"


def _extract_judgment_links(html: str, base_url: str) -> List[JudgmentLink]:
    """
    Parse all judgment links from a Kenya Law listing or search results page.
    Returns a list of JudgmentLink objects.
    """
    soup = BeautifulSoup(html, "html.parser")
    links: List[JudgmentLink] = []
    seen_hrefs: set = set()

    for anchor in soup.find_all("a", href=_AKN_HREF_RE):
        href = str(anchor.get("href", ""))
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        m = _AKN_HREF_RE.search(href)
        if not m:
            continue

        court_raw, year, citation_num, date = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
        )
        court_code = court_raw.upper()

        anchor_text = _clean_text(anchor.get_text(separator=" "))
        meta = _parse_anchor_metadata(anchor_text)

        links.append(
            JudgmentLink(
                akn_href=href,
                pdf_url=_akn_to_pdf_url(base_url, href),
                docx_url=_akn_to_docx_url(base_url, href),
                court_code=court_code,
                year=year,
                citation_number=citation_num,
                date=date,
                title=meta.get("title") or anchor_text,
                case_number=meta.get("case_number"),
                citation=meta.get("citation"),
                doc_type_label=meta.get("doc_type"),
            )
        )

    return links


def _has_next_page(html: str) -> bool:
    """Return True if a 'Next' pagination link exists on the page."""
    soup = BeautifulSoup(html, "html.parser")
    # Check rel="next" attribute first (cleanest signal)
    if soup.find("a", rel="next"):
        return True
    # Fall back to anchor text search
    for anchor in soup.find_all("a"):
        text = anchor.get_text(strip=True)
        if re.search(r"\bNext\b", text, re.I):
            return True
    return False


# ---------------------------------------------------------------------------
# Kenya Law Crawler
# ---------------------------------------------------------------------------


class KenyaLawCrawler(BaseCrawler):
    """
    Crawls new.kenyalaw.org and downloads judgment PDFs to MinIO.

    Supports two modes (set via `mode` param or sites.yaml):

    1. court   — iterate paginated court listing pages
                 /judgments/{COURT_CODE}/?page=N
                 Courts configured in sites.yaml (default: all superior courts)

    2. search  — iterate paginated search results
                 /search/?q={term}&page=N
                 Terms provided via --terms CLI flag

    Both modes parse HTML with BeautifulSoup to extract AKN judgment URLs,
    then construct PDF download URLs as {akn_url}/source.pdf.
    """

    BASE_URL = "https://new.kenyalaw.org"

    # Listing page URL templates
    COURT_LISTING_URL = "/judgments/{court_code}/"
    SEARCH_URL = "/search/"

    # Default courts to crawl when mode="court"
    DEFAULT_COURTS = ["KESC", "KECA", "KEHC", "KEELRC", "KEELC"]

    def __init__(
        self,
        site_config: dict,
        settings: Settings,
        minio_client: MinIOClient,
        terms: Optional[List[str]] = None,
        max_pages: int = 10,
        mode: str = "court",
        courts: Optional[List[str]] = None,
    ) -> None:
        super().__init__(site_config, settings, minio_client)
        self.terms = terms or []
        self.max_pages = max_pages
        self.mode = mode  # "court" | "search"
        self.courts = [c.upper() for c in courts] if courts else self.DEFAULT_COURTS

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def crawl(
        self, start_urls: Optional[List[str]] = None, depth: int = 1
    ) -> CrawlReport:
        connector = aiohttp.TCPConnector(limit=10)
        headers = {
            "User-Agent": "SheriaBot/1.0 (+https://sheriaplatform.go.ke/bot)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        timeout = aiohttp.ClientTimeout(total=90)
        report = CrawlReport()

        async with aiohttp.ClientSession(
            connector=connector, headers=headers, timeout=timeout
        ) as session:
            sem = asyncio.Semaphore(self.settings.max_concurrent_downloads)

            if self.mode == "search":
                if not self.terms:
                    logger.warning("Search mode selected but no --terms provided.")
                    return report
                tasks = [
                    self._crawl_search_term(term, session, report, sem)
                    for term in self.terms
                ]
            else:  # court mode
                tasks = [
                    self._crawl_court(court_code, session, report, sem)
                    for court_code in self.courts
                ]

            await asyncio.gather(*tasks, return_exceptions=True)

        return report

    # ------------------------------------------------------------------
    # Court-listing mode
    # ------------------------------------------------------------------

    async def _crawl_court(
        self,
        court_code: str,
        session: aiohttp.ClientSession,
        report: CrawlReport,
        sem: asyncio.Semaphore,
    ) -> None:
        court_name = COURT_NAMES.get(court_code, court_code)
        logger.info("Crawling court: %s (%s)", court_name, court_code)
        listing_path = self.COURT_LISTING_URL.format(court_code=court_code)

        for page in range(1, self.max_pages + 1):
            url = f"{self.BASE_URL}{listing_path}?page={page}"
            html = await self._fetch_html(url, session)
            if html is None:
                logger.warning("Failed to fetch %s", url)
                break

            links = _extract_judgment_links(html, self.BASE_URL)
            if not links:
                logger.debug("No judgment links on %s — stopping.", url)
                break

            logger.info(
                "[%s] page %d — found %d judgment links",
                court_code,
                page,
                len(links),
            )
            await self._process_links(links, session, report, sem)

            if not _has_next_page(html):
                logger.debug("[%s] No next page after page %d.", court_code, page)
                break

    # ------------------------------------------------------------------
    # Search mode
    # ------------------------------------------------------------------

    async def _crawl_search_term(
        self,
        term: str,
        session: aiohttp.ClientSession,
        report: CrawlReport,
        sem: asyncio.Semaphore,
    ) -> None:
        logger.info("Searching for term: '%s'", term)
        encoded_term = quote_plus(term)

        for page in range(1, self.max_pages + 1):
            url = f"{self.BASE_URL}{self.SEARCH_URL}?q={encoded_term}&page={page}"
            html = await self._fetch_html(url, session)
            if html is None:
                logger.warning("Failed to fetch search page %d for '%s'", page, term)
                break

            links = _extract_judgment_links(html, self.BASE_URL)
            if not links:
                logger.debug(
                    "No judgment links on search page %d for '%s'.", page, term
                )
                break

            logger.info(
                "[search:'%s'] page %d — found %d judgment links",
                term,
                page,
                len(links),
            )
            await self._process_links(links, session, report, sem)

            if not _has_next_page(html):
                break

    # ------------------------------------------------------------------
    # Per-link download and store
    # ------------------------------------------------------------------

    async def _process_links(
        self,
        links: List[JudgmentLink],
        session: aiohttp.ClientSession,
        report: CrawlReport,
        sem: asyncio.Semaphore,
    ) -> None:
        tasks = [self._download_and_store(jl, session, report, sem) for jl in links]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _download_and_store(
        self,
        jl: JudgmentLink,
        session: aiohttp.ClientSession,
        report: CrawlReport,
        sem: asyncio.Semaphore,
    ) -> None:
        if not self._check_robots(jl.pdf_url):
            logger.info("robots.txt blocked: %s", jl.pdf_url)
            return

        async with sem:
            report.total_urls_visited += 1
            content, filename = await self._download_file(jl.pdf_url, session)

            if content is None:
                logger.warning("Download failed: %s", jl.pdf_url)
                report.documents_failed += 1
                return

            if not validate_pdf(content):
                # PDF failed — try DOCX as fallback
                logger.debug("Not a PDF; trying DOCX fallback: %s", jl.docx_url)
                content, filename = await self._download_file(jl.docx_url, session)
                if content is None:
                    report.documents_failed += 1
                    return
                doc_type = "docx"
                filename = (
                    filename if filename.endswith(".docx") else f"{filename}.docx"
                )
            else:
                doc_type = "pdf"
                if not filename.endswith(".pdf"):
                    filename = f"{filename}.pdf"

            sha = compute_sha256(content)
            if sha in self._seen_hashes:
                report.documents_skipped_duplicate += 1
                return

            court_name = COURT_NAMES.get(jl.court_code, jl.court_code)
            meta = DocumentMetadata(
                source_url=jl.pdf_url if doc_type == "pdf" else jl.docx_url,
                sha256=sha,
                file_size=len(content),
                doc_type=doc_type,
                title=jl.title,
                court=court_name,
                year=jl.year,
                case_name=jl.title,
                case_number=jl.case_number,
                source="kenya_law",
            )

            # Prefer a deterministic filename: {court}_{year}_{citation_num}.{ext}
            stable_filename = (
                f"{jl.court_code.lower()}_{jl.year}_{jl.citation_number}.{doc_type}"
            )
            minio_path = build_minio_path(meta, stable_filename)

            if self.minio.document_exists(minio_path):
                report.documents_skipped_duplicate += 1
                self._seen_hashes.add(sha)
                return

            await self._upload(content, minio_path, meta, report)
            self._seen_hashes.add(sha)
            report.documents_downloaded += 1
            logger.info(
                "Stored [%s %s/%s] %s → %s",
                jl.court_code,
                jl.year,
                jl.citation_number,
                jl.title or stable_filename,
                minio_path,
            )

    # ------------------------------------------------------------------
    # Shared HTML fetcher
    # ------------------------------------------------------------------

    async def _fetch_html(
        self, url: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Fetch a page and return its HTML text, or None on failure."""
        resp = await self._fetch(url, session)
        if resp is None:
            return None
        try:
            return await resp.text()
        except Exception as exc:
            logger.warning("Failed to decode HTML from %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # BaseCrawler abstract method stubs (not used in primary crawl path)
    # ------------------------------------------------------------------

    async def _extract_links(
        self, response: aiohttp.ClientResponse, base_url: str
    ) -> List[str]:
        html = await response.text()
        return [
            urljoin(base_url, jl.pdf_url)
            for jl in _extract_judgment_links(html, base_url)
        ]

    async def _extract_metadata(
        self, response: aiohttp.ClientResponse, url: str
    ) -> DocumentMetadata:
        m = _AKN_HREF_RE.search(url)
        court_code = m.group(1).upper() if m else "unknown"
        year = m.group(2) if m else None
        return DocumentMetadata(
            source_url=url,
            sha256="",
            file_size=0,
            doc_type="pdf",
            court=COURT_NAMES.get(court_code, court_code),
            year=year,
            source="kenya_law",
        )


# ---------------------------------------------------------------------------
# Generic Legal Crawler (unchanged)
# ---------------------------------------------------------------------------


class GenericLegalCrawler(BaseCrawler):
    """
    BFS crawler for arbitrary websites.
    Extracts .pdf / .docx / .doc links via BeautifulSoup and downloads them.
    """

    _SUPPORTED_EXTS = (".pdf", ".docx", ".doc")

    async def _extract_links(
        self, response: aiohttp.ClientResponse, base_url: str
    ) -> List[str]:
        """Return all same-origin links found on the page."""
        try:
            html = await response.text()
        except Exception:
            return []
        soup = BeautifulSoup(html, "html.parser")
        base_parsed = urlparse(base_url)
        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = str(tag.get("href", "")).strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            full = urljoin(base_url, href)
            if urlparse(full).netloc == base_parsed.netloc:
                links.append(full)
        return list(set(links))

    async def _extract_metadata(
        self, response: aiohttp.ClientResponse, url: str
    ) -> DocumentMetadata:
        domain = urlparse(url).netloc
        ext = url.rsplit(".", 1)[-1].lower() if "." in url.split("/")[-1] else "pdf"
        return DocumentMetadata(
            source_url=url,
            sha256="",
            file_size=0,
            doc_type=ext,
            source=f"generic_{domain}",
        )

    async def crawl(self, start_urls: List[str], depth: int = 1) -> CrawlReport:
        """BFS crawl: collect document links layer by layer, then download."""
        connector = aiohttp.TCPConnector(limit=10)
        headers = {"User-Agent": "SheriaBot/1.0 (+https://sheriaplatform.go.ke/bot)"}
        timeout = aiohttp.ClientTimeout(total=60)
        report = CrawlReport()

        async with aiohttp.ClientSession(
            connector=connector, headers=headers, timeout=timeout
        ) as session:
            visited: set = set()
            frontier = list(start_urls)

            for _level in range(depth):
                next_frontier: List[str] = []
                for url in frontier:
                    if url in visited:
                        continue
                    visited.add(url)
                    if not self._check_robots(url):
                        continue

                    resp = await self._fetch(url, session)
                    if resp is None:
                        continue

                    links = await self._extract_links(resp, url)
                    doc_links = [
                        lk
                        for lk in links
                        if any(lk.lower().endswith(ext) for ext in self._SUPPORTED_EXTS)
                    ]
                    page_links = [
                        lk
                        for lk in links
                        if not any(
                            lk.lower().endswith(ext) for ext in self._SUPPORTED_EXTS
                        )
                    ]

                    _sem = asyncio.Semaphore(self.settings.max_concurrent_downloads)
                    tasks = [
                        self._process_url(doc_url, session, report)
                        for doc_url in doc_links
                        if doc_url not in visited
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    next_frontier.extend(page_links)

                frontier = [u for u in next_frontier if u not in visited]

        return report
