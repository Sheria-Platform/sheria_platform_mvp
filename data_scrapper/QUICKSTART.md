# Quickstart — Sheria Legal Scraper

Five minutes from zero to first documents in MinIO.

---

## 1. Prerequisites

| Requirement | Check |
|-------------|-------|
| Python 3.11+ | `python --version` |
| Docker + Compose | `docker-compose version` |
| Project root `docker-compose.yml` | `ls ../docker-compose.yml` |

---

## 2. Install

```bash
cd data_scrapper
pip install -r requirements.txt
```

---

## 3. Configure

```bash
cp .env.example .env
```

The defaults in `.env.example` work with the project's local Docker setup — no edits needed for development:

```env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=legal-documents
MINIO_SECURE=false
MAX_CONCURRENT_DOWNLOADS=5
DEFAULT_RATE_LIMIT_RPS=0.5
LOG_LEVEL=INFO
```

---

## 4. Start MinIO

```bash
# From the project root
docker-compose up minio -d
```

Verify: http://localhost:9001 → login `minioadmin` / `minioadmin`

---

## 5. Run

### Kenya Law — court mode (recommended first run)

Download Supreme Court judgments, one page (fast, ~2 minutes):

```bash
python scraper/main.py --crawler kenya_law --courts KESC --pages 1
```

All superior courts, 10 pages each:

```bash
python scraper/main.py --crawler kenya_law --pages 10
```

### Kenya Law — search mode

Download judgments matching keywords:

```bash
python scraper/main.py --crawler kenya_law \
  --mode search \
  --terms "land,succession,marriage" \
  --pages 5
```

### Generic web crawler

```bash
python scraper/main.py --crawler generic \
  --urls "https://new.kenyalaw.org/legislation/" \
  --depth 2
```

### Check what was stored

```bash
python scraper/main.py --report
```

---

## 6. Browse results

**MinIO console** → http://localhost:9001 → Buckets → `legal-documents`

Documents are stored at:
```
legal/kenya_law/{year}/{case-name}/judgment.pdf
legal/kenya_law/{year}/{case-name}/judgment.pdf.meta.json
```

**AWS CLI** (pointed at local MinIO):
```bash
aws --endpoint-url http://localhost:9000 \
    --no-sign-request \
    s3 ls s3://legal-documents/legal/ --recursive
```

---

## Common commands at a glance

```bash
# Kenya Law — land cases, 5 pages
python scraper/main.py --crawler kenya_law --terms "land" --pages 5

# Kenya Law — multiple topics
python scraper/main.py --crawler kenya_law \
  --terms "land,succession,marriage" --pages 10

# Generic crawler — any URL, 1 level deep
python scraper/main.py --crawler generic \
  --urls "https://example.com/legal-docs" --depth 1

# Generic crawler — multiple start URLs
python scraper/main.py --crawler generic \
  --urls "https://site1.com,https://site2.com" --depth 2

# Storage report
python scraper/main.py --report

# Debug mode (verbose logs)
LOG_LEVEL=DEBUG python scraper/main.py --crawler kenya_law --terms "land" --pages 1
```

---

## What happens under the hood

```
1. Load .env → pydantic-settings validates config
2. Connect to MinIO → create bucket if missing
3. For each search term:
   GET /search/api/documents/?q=<term>&page=1…N
   └── For each case result (concurrent, up to MAX_CONCURRENT_DOWNLOADS):
       ├── Check robots.txt
       ├── Fetch case page HTML
       ├── Extract PDF download URL
       ├── Download PDF bytes
       ├── Validate: magic bytes (%PDF-)
       ├── Compute SHA-256 → check duplicate
       └── Upload to MinIO:
           ├── legal/kenya_law/{year}/{case}/file.pdf
           └── legal/kenya_law/{year}/{case}/file.pdf.meta.json
4. Print crawl report + MinIO stats
```

---

## Adjusting speed

The crawler sends **1 request every 2 seconds** to Kenya Law by default. This is intentional — it's polite and avoids triggering rate limits.

To adjust, edit `scraper/config/sites.yaml`:

```yaml
kenya_law:
  rate_limit_rps: 0.5   # current: 1 req per 2 sec
                         # 1.0 = 1 req per sec (faster, less polite)
                         # 0.25 = 1 req per 4 sec (slower, safer)
```

---

## Troubleshooting fast path

| Problem | Fix |
|---------|-----|
| `Connection refused` on MinIO | `docker-compose up minio -d` from project root |
| `No PDF found` | Enable `LOG_LEVEL=DEBUG` and inspect HTML |
| `Invalid PDF` | Server returned HTML (rate limited?) — reduce `rate_limit_rps` |
| Files in `/tmp/sheria_scraper_temp/` | MinIO was down; re-run to upload, or use `aws s3 cp` |
| Crawl report shows 0 downloads | Check `LOG_LEVEL=DEBUG`; likely no results for that search term |

Full documentation: [README.md](./README.md)
