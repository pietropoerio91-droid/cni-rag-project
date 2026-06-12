#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from src.core.logging import setup_logging
from src.ingestion.chunker import DocumentChunker
from src.ingestion.cleaner import TextCleaner
from src.ingestion.downloader import Downloader
from src.ingestion.embedder import EmbeddingGenerator
from src.governance.public_data_filter import PublicDataFilter
from src.governance.quality_check import QualityChecker
from src.vectorstore.indexer import VectorIndexer

console = Console()


@click.command()
@click.option("--input", "input_dir", default="data/processed", help="Input processed documents directory")
@click.option("--clear/--no-clear", default=False, help="Clear existing index before building")
def build_index(input_dir: str, clear: bool):
    """Build vector index from processed documents."""
    setup_logging()

    console.print("[bold cyan]CNI RAG - Index Builder[/bold cyan]")

    if clear:
        console.print("[yellow]Clearing existing index...[/yellow]")
        indexer = VectorIndexer()
        indexer.clear_index()
        console.print("[green]  Index cleared[/green]")

    console.print(f"[yellow]Loading documents from {input_dir}...[/yellow]")
    downloader = Downloader(output_dir=input_dir)
    documents = downloader.load_documents()
    console.print(f"[green]  Loaded {len(documents)} documents[/green]")

    public_filter = PublicDataFilter()
    quality = QualityChecker()
    cleaner = TextCleaner()

    valid_docs = []
    for doc in documents:
        if not public_filter.is_public(doc.get("url", ""), doc.get("content", "")):
            continue
        ok, _ = quality.check(doc.get("content", ""))
        if not ok:
            continue
        doc["content"] = cleaner.clean(doc.get("content", ""))
        valid_docs.append(doc)
    console.print(f"[green]  Valid documents: {len(valid_docs)}[/green]")

    chunker = DocumentChunker()
    chunks = chunker.chunk_documents(valid_docs)
    console.print(f"[green]  Created {len(chunks)} chunks[/green]")

    embedder = EmbeddingGenerator()
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Embedding chunks...", total=len(chunks))
        chunks_with_embeddings = embedder.process_chunks(chunks)
        progress.update(task, completed=len(chunks))

    indexer = VectorIndexer()
    indexed_count = indexer.index_chunks(chunks_with_embeddings)
    total = indexer.count_points()

    console.print(f"[bold green]Index built successfully![/bold green]")
    console.print(f"  Documents: {len(valid_docs)}")
    console.print(f"  Chunks: {len(chunks)}")
    console.print(f"  Indexed points: {indexed_count}")
    console.print(f"  Total in collection: {total}")


if __name__ == "__main__":
    build_index()
