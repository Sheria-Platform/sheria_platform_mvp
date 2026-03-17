#!/usr/bin/env python3
"""
CLI entry point for the Sheria modular legal document scraper.

Kenya Law — court mode (default, recommended):
  python scraper/main.py --crawler kenya_law --mode court --pages 5
  python scraper/main.py --crawler kenya_law --courts KESC,KECA --pages 10

Kenya Law — search mode:
  python scraper/main.py --crawler kenya_law --mode search --terms "land,succession" --pages 5

Generic web crawler:
  python scraper/main.py --crawler generic --urls https://example.com --depth 2

Storage report:
  python scraper/main.py --report
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Ensure the data_scrapper directory is on the path so `scraper.*` imports work
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from scraper.config.settings import get_settings  # noqa: E402
from scraper.crawlers.legal_sites import (  # noqa: E402
    COURT_NAMES,
    GenericLegalCrawler,
    KenyaLawCrawler,
)
from scraper.storage.minio_client import MinIOClient  # noqa: E402

log = logging.getLogger(__name__)

console = Console()

_VALID_COURTS = list(COURT_NAMES.keys())


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_site_config(crawler_name: str) -> dict:
    config_path = Path(__file__).parent / "config" / "sites.yaml"
    with open(config_path) as fh:
        all_sites = yaml.safe_load(fh)
    return all_sites.get(crawler_name, all_sites.get("generic", {}))


def _print_report(crawl_report, minio_stats: dict) -> None:
    console.rule("[bold green]Crawl Report")
    table = Table(show_header=False, padding=(0, 2))
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("URLs visited", str(crawl_report.total_urls_visited))
    table.add_row("Documents downloaded", str(crawl_report.documents_downloaded))
    table.add_row("Duplicates skipped", str(crawl_report.documents_skipped_duplicate))
    table.add_row("Invalid files skipped", str(crawl_report.documents_skipped_invalid))
    table.add_row("Failed downloads", str(crawl_report.documents_failed))
    table.add_row("MinIO upload failures", str(len(crawl_report.upload_failures)))
    console.print(table)

    if minio_stats:
        console.rule("[bold blue]MinIO Storage")
        size_mb = minio_stats["total_bytes"] / (1024 * 1024)
        console.print(
            f"  Bucket: [bold]{minio_stats['bucket']}[/bold]  |  "
            f"Objects: [bold]{minio_stats['object_count']}[/bold]  |  "
            f"Size: [bold]{size_mb:.1f} MB[/bold]"
        )

    if crawl_report.errors:
        console.rule("[bold red]Errors (first 10)[/bold red]")
        for err in crawl_report.errors[:10]:
            console.print(f"  [red]•[/red] {err}")
        if len(crawl_report.errors) > 10:
            console.print(f"  ... and {len(crawl_report.errors) - 10} more")


async def _run_kenya_law(args, settings, minio, site_config) -> None:
    mode = getattr(args, "mode", "court")

    # Parse courts (comma-separated, uppercased)
    courts_raw = getattr(args, "courts", "") or ""
    courts = [c.strip().upper() for c in courts_raw.split(",") if c.strip()]
    if not courts:
        courts = site_config.get("courts", KenyaLawCrawler.DEFAULT_COURTS)

    invalid = [c for c in courts if c not in _VALID_COURTS]
    if invalid:
        console.print(
            f"[red]Unknown court code(s): {invalid}[/red]\nValid codes: {_VALID_COURTS}"
        )
        sys.exit(1)

    # Parse search terms (only used in search mode)
    terms_raw = getattr(args, "terms", "") or ""
    terms = [t.strip() for t in terms_raw.split(",") if t.strip()]

    if mode == "search" and not terms:
        console.print(
            "[red]Search mode requires --terms. Example: --terms 'land,succession'[/red]"
        )
        sys.exit(1)

    # Resolve ingest settings: CLI flags override env/settings
    auto_ingest = not getattr(args, "no_ingest", False)
    ingest_batch_size = getattr(args, "ingest_every", None)
    if ingest_batch_size is not None:
        if ingest_batch_size == 0:
            auto_ingest = False
        else:
            settings.ingest_batch_size = ingest_batch_size
    if not auto_ingest:
        settings.ingest_batch_size = settings.ingest_batch_size  # keep default

    # Build registry (gracefully degrade if DB is unavailable)
    registry = None
    if auto_ingest or True:  # always try registry for resumability
        try:
            from scraper.db.registry import DocumentRegistry
            registry = DocumentRegistry(settings.database_url)
            registry.ensure_tables()
        except Exception as exc:
            log.warning(
                "DocumentRegistry unavailable (%s) — falling back to MinIO-only dedup", exc
            )
            registry = None

    pages_display = str(args.pages) if args.pages > 0 else "unlimited"
    loop = asyncio.get_event_loop()

    crawler = KenyaLawCrawler(
        site_config=site_config,
        settings=settings,
        minio_client=minio,
        terms=terms,
        max_pages=args.pages,
        mode=mode,
        courts=courts,
        registry=registry,
        auto_ingest=auto_ingest,
        loop=loop,
    )

    if mode == "court":
        court_labels = [COURT_NAMES.get(c, c) for c in courts]
        console.print(
            f"[cyan]Kenya Law[/cyan] — mode: court | "
            f"courts: {court_labels} | max pages/court: {pages_display} | "
            f"auto-ingest: {'every ' + str(settings.ingest_batch_size) if auto_ingest else 'disabled'}"
        )
    else:
        console.print(
            f"[cyan]Kenya Law[/cyan] — mode: search | "
            f"terms: {terms} | max pages/term: {pages_display} | "
            f"auto-ingest: {'every ' + str(settings.ingest_batch_size) if auto_ingest else 'disabled'}"
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Crawling Kenya Law…", total=None)
        report = await crawler.crawl()
        progress.update(task, description="Crawl complete", total=1, completed=1)

    if registry is not None:
        try:
            registry.close()
        except Exception:
            pass

    stats = minio.get_bucket_stats()
    _print_report(report, stats)


async def _run_generic(args, settings, minio, site_config) -> None:
    urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    if not urls:
        console.print("[red]No URLs provided. Use --urls https://example.com[/red]")
        sys.exit(1)

    crawler = GenericLegalCrawler(
        site_config=site_config,
        settings=settings,
        minio_client=minio,
    )
    console.print(f"[cyan]Generic crawler[/cyan] — URLs: {urls}, depth: {args.depth}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Crawling…", total=None)
        report = await crawler.crawl(start_urls=urls, depth=args.depth)
        progress.update(task, description="Crawl complete", total=1, completed=1)

    stats = minio.get_bucket_stats()
    _print_report(report, stats)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sheria legal document scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--crawler",
        choices=["kenya_law", "generic"],
        help="Crawler to run",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show MinIO bucket statistics and exit",
    )

    # Kenya Law options
    kl_group = parser.add_argument_group("Kenya Law options")
    kl_group.add_argument(
        "--mode",
        choices=["court", "search"],
        default="court",
        help=(
            "court: crawl judgment listing pages by court (default). "
            "search: crawl search results by keyword (--terms required)."
        ),
    )
    kl_group.add_argument(
        "--courts",
        default="",
        metavar="CODES",
        help=(
            f"Comma-separated court codes for court mode. "
            f"Valid: {', '.join(_VALID_COURTS)}. "
            f"Default: all superior courts."
        ),
    )
    kl_group.add_argument(
        "--terms",
        default="",
        metavar="TERMS",
        help="Comma-separated search terms (required for --mode search).",
    )
    kl_group.add_argument(
        "--pages",
        type=int,
        default=10,
        metavar="N",
        help="Max pages to fetch per court/term. 0 = unlimited (crawl until no Next page). Default: 10.",
    )
    kl_group.add_argument(
        "--ingest-every",
        type=int,
        default=None,
        metavar="N",
        dest="ingest_every",
        help="Trigger ingestion every N new documents (overrides INGEST_BATCH_SIZE). 0 = disable.",
    )
    kl_group.add_argument(
        "--no-ingest",
        action="store_true",
        default=False,
        dest="no_ingest",
        help="Scrape only; skip all ingestion triggering (useful for testing/CI).",
    )

    # Generic crawler options
    gen_group = parser.add_argument_group("Generic crawler options")
    gen_group.add_argument(
        "--urls",
        default="",
        metavar="URLS",
        help="Comma-separated start URLs for the generic crawler.",
    )
    gen_group.add_argument(
        "--depth",
        type=int,
        default=2,
        metavar="N",
        help="BFS crawl depth (default: 2).",
    )

    return parser


def main() -> None:
    load_dotenv()
    settings = get_settings()
    _setup_logging(settings.log_level)

    parser = _build_parser()
    args = parser.parse_args()

    minio = MinIOClient(settings)
    try:
        minio.ensure_bucket()
    except Exception as exc:
        console.print(f"[red]MinIO connection failed:[/red] {exc}")
        console.print(
            "Ensure MinIO is running and check "
            "MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY in your .env file."
        )
        sys.exit(1)

    if args.report:
        stats = minio.get_bucket_stats()
        size_mb = stats["total_bytes"] / (1024 * 1024)
        console.print(
            f"Bucket: [bold]{stats['bucket']}[/bold]  |  "
            f"Objects: [bold]{stats['object_count']}[/bold]  |  "
            f"Size: [bold]{size_mb:.1f} MB[/bold]"
        )
        return

    if not args.crawler:
        parser.print_help()
        sys.exit(0)

    site_config = _load_site_config(args.crawler)

    if args.crawler == "kenya_law":
        asyncio.run(_run_kenya_law(args, settings, minio, site_config))
    elif args.crawler == "generic":
        asyncio.run(_run_generic(args, settings, minio, site_config))


if __name__ == "__main__":
    main()
