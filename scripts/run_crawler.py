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
@click.option("--max-pages", default=100, help="Maximum pages to crawl")
@click.option("--max-depth", default=3, help="Maximum crawl depth")
@click.option("--output", default="data/raw", help="Output directory for raw data")
@click.option("--delay", default=1.0, help="Delay between requests (seconds)")
def run_crawler(max_pages: int, max_depth: int, output: str, delay: float):
    """Crawl the CNI website and download documents."""
    setup_logging()
    logger = logging.getLogger(__name__)

    console.print("[bold cyan]CNI RAG - Web Crawler[/bold cyan]")
    console.print(f"  Max pages: {max_pages}")
    console.print(f"  Max depth: {max_depth}")
    console.print(f"  Output: {output}")

    crawler = CNICrawler()
    crawler.max_pages = max_pages
    crawler.max_depth = max_depth
    crawler.delay = delay

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[yellow]Crawling CNI website...", total=None)
        documents = asyncio.run(crawler.crawl())
        progress.update(task, completed=True)

    downloader = Downloader(output_dir=output)
    saved_paths = downloader.save_documents(documents)

    console.print(f"[green]Crawl complete![/green]")
    console.print(f"  Pages visited: {len(crawler.visited)}")
    console.print(f"  Documents saved: {len(saved_paths)}")
    console.print(f"  Output directory: {output}")


if __name__ == "__main__":
    run_crawler()
