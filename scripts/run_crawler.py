#!/usr/bin/env python3
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.logging import setup_logging
from src.ingestion.crawler import CNICrawler
from src.ingestion.downloader import Downloader

console = Console()


@click.command()
@click.option("--max-pages", default=None, type=int, help="Maximum pages to crawl (default: from config)")
@click.option("--max-depth", default=None, type=int, help="Maximum crawl depth (default: from config)")
@click.option("--output", default="data/raw", help="Output directory for raw data")
@click.option("--delay", default=None, type=float, help="Delay between requests in seconds (default: from config)")
@click.option("--priority-paths", default=None, help="Comma-separated list of priority URL paths")
@click.option("--priority-max-depth", default=None, type=int, help="Max depth for priority paths (default: from config)")
@click.option("--no-raw-files", is_flag=True, help="Skip saving raw HTML/PDF files")
def run_crawler(max_pages, max_depth, output, delay, priority_paths, priority_max_depth, no_raw_files):
    """Crawl the CNI website and download documents."""
    setup_logging()
    logger = logging.getLogger(__name__)

    crawler = CNICrawler()
    if max_pages is not None:
        crawler.max_pages = max_pages
    if max_depth is not None:
        crawler.max_depth = max_depth
    if delay is not None:
        crawler.delay = delay
    if priority_paths is not None:
        crawler.priority_paths = [p.strip() for p in priority_paths.split(",")]
    if priority_max_depth is not None:
        crawler.priority_max_depth = priority_max_depth

    console.print("[bold cyan]CNI RAG - Web Crawler[/bold cyan]")
    console.print(f"  Max pages: {crawler.max_pages}")
    console.print(f"  Max depth: {crawler.max_depth}")
    console.print(f"  Priority paths: {crawler.priority_paths}")
    console.print(f"  Priority max depth: {crawler.priority_max_depth}")
    console.print(f"  Output: {output}")
    if no_raw_files:
        console.print(f"  Raw files: disabled")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[yellow]Crawling CNI website...", total=None)
        if no_raw_files:
            documents = asyncio.run(_crawl_no_raw(crawler))
        else:
            documents = asyncio.run(crawler.crawl())
        progress.update(task, completed=True)

    downloader = Downloader(output_dir=output)
    saved_paths = downloader.save_documents(documents)

    html_dir = Path(output) / "html"
    pdf_dir = Path(output) / "pdf"
    html_count = len(list(html_dir.glob("*.html"))) if html_dir.exists() else 0
    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0

    console.print(f"[green]Crawl complete![/green]")
    console.print(f"  Pages visited: {len(crawler.visited)}")
    console.print(f"  JSON documents saved: {len(saved_paths)}")
    console.print(f"  HTML files saved: {html_count}")
    console.print(f"  PDF files saved: {pdf_count}")
    console.print(f"  Output directory: {output}")


async def _crawl_no_raw(crawler: CNICrawler) -> list[dict[str, Any]]:
    """Crawl but strip raw content before returning (memory saving)."""
    docs = await crawler.crawl()
    for doc in docs:
        doc.pop("raw_html", None)
        doc.pop("raw_pdf", None)
    return docs


if __name__ == "__main__":
    run_crawler()
