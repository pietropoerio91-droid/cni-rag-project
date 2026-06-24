#!/usr/bin/env python3
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from src.core.logging import setup_logging
from src.governance.public_data_filter import PublicDataFilter
from src.governance.quality_check import QualityChecker
from src.ingestion.chunker import DocumentChunker
from src.ingestion.cleaner import TextCleaner
from src.ingestion.crawler import CNICrawler
from src.ingestion.downloader import Downloader
from src.ingestion.embedder import EmbeddingGenerator
from src.vectorstore.indexer import VectorIndexer

console = Console()


@click.command()
@click.option("--crawl/--no-crawl", default=True, help="Run crawler before ingestion")
@click.option("--max-pages", default=1000, help="Maximum pages to crawl")
@click.option("--input", "input_dir", default="data/raw", help="Input directory with raw documents")
def run_ingestion(crawl: bool, max_pages: int, input_dir: str):
    """Process crawled documents: clean, chunk, embed, and index."""
    setup_logging()
    logger = logging.getLogger(__name__)

    console.print("[bold cyan]CNI RAG - Ingestion Pipeline[/bold cyan]")

    documents = []

    if crawl:
        console.print("[yellow]Phase 1: Crawling CNI website...[/yellow]")
        crawler = CNICrawler()
        crawler.max_pages = max_pages
        documents = asyncio.run(crawler.crawl())
        downloader = Downloader(output_dir=input_dir)
        downloader.save_documents(documents)
        console.print(f"[green]  Crawled {len(documents)} documents[/green]")
    else:
        console.print(f"[yellow]Phase 1: Loading documents from {input_dir}...[/yellow]")
        downloader = Downloader(output_dir=input_dir)
        documents = downloader.load_documents()
        console.print(f"[green]  Loaded {len(documents)} documents[/green]")

    public_filter = PublicDataFilter()
    quality = QualityChecker()
    cleaner = TextCleaner()

    console.print("[yellow]Phase 2: Filtering and cleaning...[/yellow]")
    valid_docs = []
    for doc in documents:
        url = doc.get("url", "")
        if not public_filter.is_public(url, doc.get("content", "")):
            logger.warning(f"Filtered by public_data_filter: {url}")
            continue
        ok, issues = quality.check(doc.get("content", ""))
        if not ok:
            logger.warning(f"Filtered by quality check for {url}: {issues}")
            continue
        doc["content"] = cleaner.clean(doc.get("content", ""))
        doc["meta"]["category"] = public_filter.categorize(url, doc.get("content", ""))
        valid_docs.append(doc)
    console.print(f"[green]  Valid documents: {len(valid_docs)}[/green]")

    console.print("[yellow]Phase 3: Chunking...[/yellow]")
    chunker = DocumentChunker()
    chunks = chunker.chunk_documents(valid_docs)
    console.print(f"[green]  Created {len(chunks)} chunks[/green]")

    console.print("[yellow]Phase 4: Generating embeddings...[/yellow]")
    embedder = EmbeddingGenerator()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Embedding chunks...", total=len(chunks))
        chunks_with_embeddings = embedder.process_chunks(chunks)
        progress.update(task, completed=len(chunks))
    console.print(f"[green]  Embeddings generated[/green]")

    console.print("[yellow]Phase 5: Indexing into Qdrant...[/yellow]")
    indexer = VectorIndexer()
    indexed_count = indexer.index_chunks(chunks_with_embeddings)
    console.print(f"[green]  Indexed {indexed_count} vectors[/green]")

    total = indexer.count_points()
    console.print(f"[bold green]Ingestion complete! Total indexed: {total}[/bold green]")


if __name__ == "__main__":
    run_ingestion()
