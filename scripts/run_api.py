#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import uvicorn
from rich.console import Console

from src.core.logging import setup_logging

console = Console()


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on code changes")
def run_api(host: str, port: int, reload: bool):
    """Start the CNI RAG API server."""
    setup_logging()

    console.print("[bold cyan]CNI RAG API Server[/bold cyan]")
    console.print(f"  Host: {host}")
    console.print(f"  Port: {port}")
    console.print(f"  Reload: {reload}")
    console.print()
    console.print("[yellow]Make sure LM Studio is running on http://localhost:1234[/yellow]")
    console.print()

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_excludes=["*node_modules*", "*.git/*"],
        log_level="info",
    )


if __name__ == "__main__":
    run_api()
