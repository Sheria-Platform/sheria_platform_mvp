# services/api/app/tools/web_search.py
"""Kenya Law live web search tool.

Fetches search results from https://new.kenyalaw.org/ for queries not
satisfied by the local Qdrant/Neo4j index.  Only activated when the
request includes ``web_search=True``.

All errors (timeout, HTTP failure, parse failure) return a plain-English
string so the LangGraph pipeline never crashes.
"""

import json
import logging
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from services.api.app.clients.ollama_client import ollama_client

logger = logging.getLogger(__name__)

_BASE_SEARCH_URL = "https://new.kenyalaw.org/search/"

# Mirrors the graph_search.py pattern: extract structured search terms before
# hitting the external site so the query is concise and keyword-focused rather
# than a full conversational sentence.
_KEYWORD_EXTRACTION_PROMPT = """
You are a Kenya Law search assistant.
Extract the most effective search keywords from the legal question below.
Prioritise: case citations, court names, legal principles, party names, and year ranges.
Remove filler words, question structure, and conversational phrasing.

Output JSON only:
{
    "keywords": ["keyword1", "keyword2", "..."],
    "search_string": "compact keyword string optimised for a search engine"
}
"""
_TIMEOUT_SECONDS = 10.0
_MAX_RESULTS = 5
_SNIPPET_MAX_CHARS = 300
_HEADERS = {
    "User-Agent": (
        "SheriaBot/1.0 (+https://sheriaplatform.go.ke; judicial-research-assistant)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-KE,en;q=0.9",
}


async def _extract_search_keywords(query: str) -> str:
    """Use the LLM to distil a conversational query into compact search keywords.

    Follows the same pattern as ``graph_search.search_graph_tool``: an LLM
    call structures the input before it reaches the external system, producing
    a tighter keyword string that search engines handle better than full sentences.

    Falls back to the original ``query`` on any LLM or parse error so the
    search always proceeds.

    Args:
        query: The refined query from the planner (may be a full sentence).

    Returns:
        A compact keyword string, e.g. ``"adverse possession Kenya 2024 Supreme Court"``.
    """
    try:
        response_text = await ollama_client.chat_completion(
            messages=[
                {"role": "system", "content": _KEYWORD_EXTRACTION_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            json_mode=True,
        )
        data = json.loads(response_text)
        search_string: str = data.get("search_string", "").strip()
        if search_string:
            logger.info(
                "Kenya Law keyword extraction",
                extra={"original": query, "keywords": search_string},
            )
            return search_string
    except Exception as exc:
        logger.warning(
            "Keyword extraction failed, using raw query",
            extra={"error": str(exc)},
        )
    return query


async def search_kenya_law_web(query: str) -> str:
    """Scrape new.kenyalaw.org for the top results matching query.

    Follows a two-step pattern (identical to ``graph_search.search_graph_tool``):
    1. Extract compact search keywords from the query via the LLM.
    2. Fetch results from Kenya Law using those keywords.

    This ensures a conversational sentence like "What is the test for adverse
    possession in Kenya as applied in recent 2024 Supreme Court cases?" becomes
    an effective search string like "adverse possession Kenya 2024 Supreme Court".

    Args:
        query: The refined legal search query from the planner.

    Returns:
        Formatted numbered list of up to 5 results (title, URL, snippet),
        or a plain-English error message if the search fails.
    """
    # Step 1 — keyword extraction (mirrors graph_search entity extraction)
    search_string = await _extract_search_keywords(query)

    url = f"{_BASE_SEARCH_URL}?q={urllib.parse.quote_plus(search_string)}"
    logger.info(
        "Kenya Law web search",
        extra={"url": url, "query": query, "search_string": search_string},
    )

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException:
        return (
            f"Kenya Law web search timed out after {_TIMEOUT_SECONDS}s "
            f"for query: {query!r}"
        )
    except httpx.HTTPStatusError as exc:
        return (
            f"Kenya Law web search returned HTTP {exc.response.status_code} "
            f"for: {url}"
        )
    except Exception as exc:
        logger.warning("Kenya Law web search error", extra={"error": str(exc)})
        return f"Kenya Law web search failed: {exc!s}"

    soup = BeautifulSoup(resp.text, "lxml")
    results = _extract_results(soup)

    if not results:
        return (
            f"Kenya Law web search returned no results for keywords: {search_string!r} "
            f"(original query: {query!r}). "
            "The site may have changed its HTML structure or the query returned zero hits."
        )

    lines = [f"Kenya Law Web Search Results for: {search_string!r}\n"]
    for i, r in enumerate(results[:_MAX_RESULTS], 1):
        lines.append(
            f"{i}. {r['title']}\n"
            f"   URL: {r['url']}\n"
            f"   Excerpt: {r['snippet']}\n"
        )
    return "\n".join(lines)


def _extract_results(soup: BeautifulSoup) -> list[dict]:
    """Parse search result cards from the Kenya Law search page.

    Uses a three-level cascade to remain resilient to minor HTML changes:
    1. ``<article>`` tags — common in Wagtail/Django CMS sites.
    2. ``<div>`` elements whose class contains the substring "result".
    3. Fallback: any ``<h2>`` / ``<h3>`` that contains or is followed by an ``<a>``.
    """
    results: list[dict] = []

    # Strategy 1: <article> elements
    for article in soup.find_all("article"):
        entry = _parse_card(article)
        if entry:
            results.append(entry)
        if len(results) >= _MAX_RESULTS:
            return results

    # Strategy 2: <div class*="result">
    if not results:
        def _has_result_class(c: object) -> bool:
            if not c:
                return False
            text = c if isinstance(c, str) else " ".join(c)  # type: ignore[arg-type]
            return "result" in text.lower()

        for div in soup.find_all("div", class_=_has_result_class):
            entry = _parse_card(div)
            if entry:
                results.append(entry)
            if len(results) >= _MAX_RESULTS:
                return results

    # Strategy 3: heading + adjacent link fallback
    if not results:
        for heading in soup.find_all(["h2", "h3"]):
            link = heading.find("a") or heading.find_next_sibling("a")
            if not link:
                continue
            title = heading.get_text(strip=True)
            href = _absolute_url(str(link.get("href") or ""))
            if not href or not title:
                continue
            results.append({"title": title, "url": href, "snippet": ""})
            if len(results) >= _MAX_RESULTS:
                return results

    return results


def _parse_card(element) -> dict | None:
    """Extract title, url, and snippet from a single result card element.

    Returns ``None`` if the element lacks the minimum required fields.
    """
    link = element.find("a", href=True)
    if not link:
        return None

    # Title: prefer explicit heading, fall back to link text
    heading = element.find(["h2", "h3", "h4"])
    title = (heading.get_text(strip=True) if heading else None) or link.get_text(
        strip=True
    )
    if not title:
        return None

    raw_href = link.get("href") or ""
    href = _absolute_url(str(raw_href))
    if not href:
        return None

    p = element.find("p")
    snippet = p.get_text(strip=True)[:_SNIPPET_MAX_CHARS] if p else ""

    return {"title": title, "url": href, "snippet": snippet}


def _absolute_url(href: str) -> str:
    """Ensure the URL is absolute, prefixing the Kenya Law origin if relative."""
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return f"https://new.kenyalaw.org{href if href.startswith('/') else '/' + href}"
