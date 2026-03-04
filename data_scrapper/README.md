# Sheria Legal Document Scraper

Async, modular web scraper for collecting Kenya Law Reports and other legal documents, with direct upload to MinIO (S3-compatible) object storage.

---

## Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [CLI Usage](#cli-usage)
- [MinIO Storage Layout](#minio-storage-layout)
- [Extending the Scraper](#extending-the-scraper)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
data_scrapper/
├── data_scrapper.py          ← original scraper (unchanged, local disk + PostgreSQL)
├── requirements.txt
├── .env.example
└── scraper/
    ├── main.py               ← CLI entry point
    ├── config/
    │   ├── settings.py       ← env-var config (pydantic-settings)
    │   └── sites.yaml        ← per-site crawl parameters
    ├── crawlers/
    │   ├── base.py           ← abstract async BaseCrawler
    │   └── legal_sites.py    ← KenyaLawCrawler, GenericLegalCrawler
    ├── storage/
    │   └── minio_client.py   ← boto3 MinIO wrapper
    ├── parsers/
    │   └── document_parser.py ← DocumentMetadata, MinIO path builder
    └── utils/
        ├── rate_limiter.py   ← async token-bucket rate limiter
        └── validators.py     ← magic-byte validation, SHA-256, MIME detection
```

### Data flow

```
CLI (main.py)
  │
  ▼
Crawler (KenyaLawCrawler | GenericLegalCrawler)
  │  aiohttp session, per-domain rate limiting, robots.txt check
  │
  ├── Kenya Law — court mode (default):
  │     GET /judgments/{COURT_CODE}/?page=N   (HTML listing page)
  │     → BeautifulSoup: find all <a href="/akn/ke/judgment/...">
  │     → construct PDF URL: {akn_href}/source.pdf
  │     → download PDF bytes (DOCX fallback if PDF fails)
  │
  ├── Kenya Law — search mode:
  │     GET /search/?q={term}&page=N          (HTML search results)
  │     → same AKN link extraction as court mode
  │
  └── Generic path:
        BFS crawl from start URLs
        → extract same-origin links
        → filter for .pdf / .docx / .doc
        → download file bytes
  │
  ▼
Validators (magic bytes → SHA-256 → duplicate check)
  │
  ▼
DocumentMetadata  →  build_minio_path()
  │
  ▼
MinIOClient
  ├── upload_document()       → legal/{source}/{year}/{case}/{file}.pdf
  └── upload_metadata_json()  → legal/{source}/{year}/{case}/{file}.pdf.meta.json
```

### Kenya Law site structure (discovered Feb 2026)

| Resource | URL pattern |
|----------|------------|
| Court listing | `/judgments/{COURT}/?page=N` |
| Search results | `/search/?q={term}&page=N` |
| Individual judgment | `/akn/ke/judgment/{court}/{year}/{num}/eng@{date}` |
| PDF download | `{judgment_url}/source.pdf` |
| DOCX download | `{judgment_url}/source` |

**No public JSON/REST API is available.** The crawler parses HTML listing pages to extract AKN document links.

| Court Code | Court Name |
|-----------|-----------|
| `KESC` | Supreme Court of Kenya |
| `KECA` | Court of Appeal |
| `KEHC` | High Court |
| `KEELRC` | Employment and Labour Relations Court |
| `KEELC` | Environment and Land Court |
| `KEIC` | Industrial Court |

### Retry and rate-limiting

| Concern | Implementation |
|---------|---------------|
| Rate limiting | Per-domain async token-bucket (`AsyncRateLimiter`) |
| Network retry | 3 attempts, exponential backoff: 1 s → 2 s → 4 s |
| 401 / 403 | Raises `AuthenticationError`, stops the crawler |
| robots.txt | Checked before every download; unreachable = allow |
| MinIO down | Falls back to `$TMPDIR/sheria_scraper_temp/` |
| Duplicate files | In-memory SHA-256 set + MinIO `head_object` check |

---

## Quick Start

### Prerequisites

- Python 3.11+
- MinIO running locally (`docker-compose up minio -d` from the project root)
- A copy of `.env` with MinIO credentials

### 1. Install dependencies

```bash
cd data_scrapper
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
```

Defaults in `.env.example` match the project's `docker-compose.yml` MinIO service, so they work out of the box for local development.

### 3. Start MinIO

```bash
# From the project root
docker-compose up minio -d
```

MinIO console: http://localhost:9001 (login: `minioadmin` / `minioadmin`)

### 4. Run the Kenya Law crawler

```bash
cd data_scrapper
python scraper/main.py --crawler kenya_law --terms "land,succession" --pages 2
```

Expected output:

```
Kenya Law crawler — terms: ['land', 'succession'], max pages/term: 2
╭──────────────────────────╮
│ Crawl Report             │
├──────────────────────────┤
│ URLs visited          12 │
│ Documents downloaded   8 │
│ Duplicates skipped     0 │
│ Invalid files skipped  1 │
│ Failed downloads       0 │
│ MinIO upload failures  0 │
╰──────────────────────────╯
Bucket: legal-documents  |  Objects: 16  |  Size: 24.3 MB
```

### 5. Verify storage

```bash
python scraper/main.py --report
```

Browse documents in the MinIO console under the `legal-documents` bucket.

---

## Configuration Reference

### Environment variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO host and port |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `legal-documents` | Bucket name (created automatically) |
| `MINIO_SECURE` | `false` | Use HTTPS (`true`) or HTTP (`false`) |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL URL (reserved for future use) |
| `MAX_CONCURRENT_DOWNLOADS` | `5` | Semaphore limit on parallel downloads |
| `DEFAULT_RATE_LIMIT_RPS` | `0.5` | Fallback rate limit (requests/second) |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

> **Production note**: Set `MINIO_SECURE=true` and use strong credentials. The defaults are development-only.

### Per-site crawl config (`scraper/config/sites.yaml`)

```yaml
kenya_law:
  base_url: "https://new.kenyalaw.org"
  api_endpoint: "/search/api/documents/"
  rate_limit_rps: 0.5    # 1 request per 2 seconds
  max_depth: 2
  robots_txt: true        # respect robots.txt
  file_types: [pdf]

generic:
  rate_limit_rps: 0.3    # conservative for unknown sites
  max_depth: 3
  robots_txt: true
  file_types: [pdf, docx, doc]
```

To adjust rate limiting for Kenya Law, edit `rate_limit_rps` in `sites.yaml`. The value is requests per second — `0.5` means one request every two seconds.

---

## CLI Usage

Run from the `data_scrapper/` directory.

### Kenya Law — court mode (default, recommended)

Crawls paginated judgment listing pages per court. No search terms needed.

```bash
# All superior courts, 5 pages each (~50 requests per court)
python scraper/main.py --crawler kenya_law --pages 5

# Specific courts only
python scraper/main.py --crawler kenya_law --courts "KESC,KECA" --pages 10

# Single court, one page (fast test run)
python scraper/main.py --crawler kenya_law --courts KEHC --pages 1
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `court` | `court` (listing pages) or `search` (keyword search) |
| `--courts` | all 5 superior courts | Comma-separated codes: `KESC KECA KEHC KEELRC KEELC` |
| `--pages` | `10` | Max listing pages per court |

### Kenya Law — search mode

Crawls keyword search results at `/search/?q={term}&page=N`.

```bash
python scraper/main.py --crawler kenya_law \
  --mode search \
  --terms "land,succession,marriage" \
  --pages 5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | — | Must be `search` |
| `--terms` | _(required)_ | Comma-separated search keywords |
| `--pages` | `10` | Max search result pages per term |

### Generic web crawler

BFS-crawls any website and downloads linked PDF/DOCX files.

```bash
python scraper/main.py --crawler generic \
  --urls "https://example.com/legal-resources" \
  --depth 2
```

| Flag | Default | Description |
|------|---------|-------------|
| `--urls` | _(required)_ | Comma-separated start URLs |
| `--depth` | `2` | How many link levels deep to crawl |

### Storage report

```bash
python scraper/main.py --report
```

### Verbose logging

```bash
LOG_LEVEL=DEBUG python scraper/main.py --crawler kenya_law --courts KESC --pages 1
```

---

## MinIO Storage Layout

Every downloaded document produces two objects in MinIO:

```
legal/
└── {source}/
    └── {year}/
        └── {case_slug}/
            ├── {filename}.pdf
            └── {filename}.pdf.meta.json
```

**Examples:**

```
legal/kenya_law/2024/republic_v_kamau/judgment.pdf
legal/kenya_law/2024/republic_v_kamau/judgment.pdf.meta.json

legal/generic_kenyalaw_org/undated/document/exhibit_a.pdf
legal/generic_kenyalaw_org/undated/document/exhibit_a.pdf.meta.json
```

**Metadata JSON** (`*.meta.json`) contains:

```json
{
  "source_url": "https://new.kenyalaw.org/.../judgment.pdf",
  "sha256": "a3f9...",
  "file_size": 204800,
  "doc_type": "pdf",
  "jurisdiction": "Kenya",
  "download_date": "2026-02-27T08:00:00+00:00",
  "title": "Republic v Kamau",
  "court": "High Court",
  "year": "2024",
  "case_name": "Republic v Kamau",
  "case_number": "HC CR 123/2024",
  "source": "kenya_law"
}
```

### Querying stored documents

```bash
# List Kenya Law 2024 documents via AWS CLI (pointed at MinIO)
aws --endpoint-url http://localhost:9000 s3 ls s3://legal-documents/legal/kenya_law/2024/ \
  --recursive
```

---

## Extending the Scraper

### Adding a new crawler

1. Add a config block to `scraper/config/sites.yaml`:

```yaml
klr_online:
  base_url: "https://klronline.com"
  rate_limit_rps: 0.3
  max_depth: 2
  robots_txt: true
  file_types: [pdf]
```

2. Subclass `BaseCrawler` in `scraper/crawlers/legal_sites.py`:

```python
class KLROnlineCrawler(BaseCrawler):

    async def _extract_links(
        self, response: aiohttp.ClientResponse, base_url: str
    ) -> list[str]:
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        # return list of same-origin URLs
        ...

    async def _extract_metadata(
        self, response: aiohttp.ClientResponse, url: str
    ) -> DocumentMetadata:
        return DocumentMetadata(
            source_url=url,
            sha256="",        # filled in by _build_metadata
            file_size=0,      # filled in by _build_metadata
            doc_type="pdf",
            source="klr_online",
        )
```

3. Wire it into `main.py`:

```python
elif crawler_name == "klr_online":
    asyncio.run(_run_generic(args, settings, minio,
                             _load_site_config("klr_online")))
```

### DocumentMetadata fields

| Field | Type | Source |
|-------|------|--------|
| `source_url` | `str` | PDF download URL |
| `sha256` | `str` | Computed by validators |
| `file_size` | `int` | `len(content)` |
| `doc_type` | `str` | File extension |
| `title` | `str` | Extracted from API / HTML |
| `court` | `str` | Extracted from API / HTML |
| `year` | `str` | Parsed from date field |
| `case_name` | `str` | Same as title for Kenya Law |
| `case_number` | `str` | Docket number |
| `source` | `str` | Crawler identifier |
| `jurisdiction` | `str` | Defaults to `"Kenya"` |

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| `_seen_hashes` is in-memory | Restarting the crawler re-fetches URLs (MinIO-level dedup still prevents re-upload, but wastes bandwidth) | Run in a single long session; MinIO `head_object` check still catches re-uploads |
| robots.txt check is synchronous | On slow servers, robots.txt parsing can briefly block the event loop | Acceptable for typical usage; avoid crawling sites with extremely slow `robots.txt` endpoints |
| No retry on MinIO upload | If MinIO is temporarily unavailable, documents fall back to `$TMPDIR/sheria_scraper_temp/` and are not retried | Check fallback directory after the run and re-upload manually |
| Generic crawler metadata is minimal | Documents from generic sites have no court/case metadata; MinIO paths default to `undated/document/` | Prefer `KenyaLawCrawler` for Kenya Law content; generic crawler is for other sources |
| `max_depth` in `sites.yaml` is not enforced | CLI `--depth` overrides config; site YAML value is informational only | Always pass `--depth` on the CLI for generic crawls |
| `DATABASE_URL` is configured but unused | Setting it has no effect in the current scraper modules | Reserved for a future database-indexing step |
| `tqdm` and `psycopg2-binary` are in requirements but unused | Minor extra install size | Safe to ignore; will be wired in future work |

---

## Troubleshooting

### `MinIO connection failed`

```
MinIO connection failed: ... Connection refused
Check MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY in your .env file.
```

- Confirm MinIO is running: `docker ps | grep minio`
- Check the endpoint matches: `MINIO_ENDPOINT=localhost:9000` (no `http://` prefix)
- If running MinIO on a remote host, set the correct IP/hostname

### `No PDF found on <url>`

The case page exists but no download link was detected. This can happen when Kenya Law updates their page HTML. Enable debug logs to inspect the page:

```bash
LOG_LEVEL=DEBUG python scraper/main.py --crawler kenya_law --terms "land" --pages 1
```

Look for `extract_pdf_url` in the output. The function checks three link patterns; if none match, update `_extract_pdf_url()` in `scraper/crawlers/legal_sites.py`.

### `Invalid PDF (bad magic bytes)`

The server returned HTML (likely a login/error page) instead of a PDF. This can happen when:
- The case requires authentication
- The PDF URL has expired
- Rate limiting triggered a redirect

Reduce `rate_limit_rps` in `sites.yaml` and re-run.

### `robots.txt blocked`

The URL is disallowed by the site's `robots.txt`. The crawler correctly skips it. Do not set `robots_txt: false` in `sites.yaml` unless you have explicit permission from the site owner.

### Local fallback files not uploaded to MinIO

After a MinIO failure, recovered files are in `$TMPDIR/sheria_scraper_temp/`. Re-upload them manually:

```bash
# Using the AWS CLI pointed at MinIO
aws --endpoint-url http://localhost:9000 s3 cp \
  /tmp/sheria_scraper_temp/legal/ \
  s3://legal-documents/legal/ \
  --recursive
```

### Progress bar disappears without a summary

The progress bar is transient (clears on completion). The crawl report table prints immediately after. If the terminal is cleared before you read it, re-run `--report`:

```bash
python scraper/main.py --report
```
