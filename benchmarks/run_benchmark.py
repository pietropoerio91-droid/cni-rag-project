#!/usr/bin/env python3
"""
Benchmarking script for CNI RAG system.

Tests different configurations (chunk_size, top_k, reranker on/off, embedding models)
and computes standard IR metrics: MRR, Recall@k, Precision@k.

Usage:
    python benchmarks/run_benchmark.py
    python benchmarks/run_benchmark.py --configs benchmark_configs.json
"""
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from src.core.config_loader import ConfigLoader
from src.core.model_factory import ModelFactory
from src.ingestion.chunker import DocumentChunker
from src.ingestion.cleaner import TextCleaner
from src.ingestion.downloader import Downloader
from src.ingestion.embedder import EmbeddingGenerator
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.prompt_builder import PromptBuilder
from src.rag.reranker import Reranker
from src.vectorstore.indexer import VectorIndexer

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    name: str
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 5
    use_reranker: bool = True
    rerank_top_k: int = 3
    embedding_model: str = "all-MiniLM-L6-v2"
    score_threshold: float = 0.0


@dataclass
class BenchmarkResult:
    config_name: str
    metrics: dict[str, float]
    avg_latency_ms: float
    total_queries: int
    config: dict[str, Any]


TEST_QUERIES: list[dict[str, Any]] = [
    # (query, expected_category, expected_keywords_in_response)
    {"q": "Quali sono gli organi del Consiglio Nazionale degli Ingegneri?", "cat": "organi", "keywords": ["consiglio", "presidente", "organi"]},
    {"q": "Come funziona la formazione continua per gli ingegneri?", "cat": "formazione", "keywords": ["cfp", "crediti", "formazione"]},
    {"q": "Quali commissioni tecniche esistono presso il CNI?", "cat": "commissioni", "keywords": ["commissione", "comitato"]},
    {"q": "Cosa dice il codice deontologico degli ingegneri?", "cat": "normativa", "keywords": ["deontologico", "codice", "norme"]},
    {"q": "Quali sono i servizi offerti dal CNI agli iscritti?", "cat": "servizi", "keywords": ["servizi", "sportello"]},
    {"q": "Come contattare il Consiglio Nazionale degli Ingegneri?", "cat": "contatti", "keywords": ["email", "telefono", "sede"]},
    {"q": "Quali sono i requisiti per l'iscrizione all'albo?", "cat": "albo", "keywords": ["albo", "iscrizione", "requisiti"]},
    {"q": "Normativa recente per la professione di ingegnere", "cat": "normativa", "keywords": ["decreto", "legge", "normativa"]},
    {"q": "Chi è l'attuale presidente del CNI?", "cat": "organi", "keywords": ["presidente"]},
    {"q": "Quanti CFP servono ogni anno per la formazione?", "cat": "formazione", "keywords": ["cfp", "credito"]},
]


class RAGBenchmark:
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self._setup_components()

    def _setup_components(self):
        rag_cfg = ConfigLoader.get_rag_config()
        rag_cfg["chunking"]["chunk_size"] = self.config.chunk_size
        rag_cfg["chunking"]["chunk_overlap"] = self.config.chunk_overlap
        rag_cfg["retrieval"]["top_k"] = self.config.top_k
        rag_cfg["retrieval"]["score_threshold"] = self.config.score_threshold
        rag_cfg["reranking"]["enabled"] = self.config.use_reranker
        rag_cfg["reranking"]["top_k"] = self.config.rerank_top_k

        # Force config reload
        ConfigLoader._instances.pop("rag_config", None)

        self.embeddings = ModelFactory.create_embeddings()
        self.retriever = HybridRetriever(self.embeddings)
        self.reranker = Reranker() if self.config.use_reranker else None

    def run_query(self, query: str) -> dict[str, Any]:
        start = time.perf_counter()
        results = self.retriever.retrieve(query)
        if self.reranker and self.config.use_reranker:
            results = self.reranker.rerank(query, results)
        latency = (time.perf_counter() - start) * 1000
        return {"results": results, "latency_ms": latency}

    def evaluate(self, queries: list[dict[str, Any]]) -> BenchmarkResult:
        latencies: list[float] = []
        all_metrics: dict[str, float] = {
            "mrr": 0.0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "precision_at_1": 0.0,
            "precision_at_3": 0.0,
            "classification_accuracy": 0.0,
        }

        for qdata in queries:
            query = qdata["q"]
            expected_cat = qdata.get("cat", "")
            result = self.run_query(query)
            latencies.append(result["latency_ms"])
            docs = result["results"]

            # Category classification accuracy
            from src.rag.query_classifier import QueryClassifier
            qc = QueryClassifier()
            predicted_cat = qc.classify(query)
            if predicted_cat == expected_cat:
                all_metrics["classification_accuracy"] += 1.0

            # MRR: reciprocal rank of first relevant doc
            for rank, doc in enumerate(docs[:10], 1):
                content = doc.get("content", "").lower()
                if any(kw.lower() in content for kw in qdata.get("keywords", [])):
                    all_metrics["mrr"] += 1.0 / rank
                    if rank == 1:
                        all_metrics["recall_at_1"] += 1.0
                    if rank <= 3:
                        all_metrics["recall_at_3"] += 1.0
                    if rank <= 5:
                        all_metrics["recall_at_5"] += 1.0
                    break

            # Precision@k for top results
            if docs:
                relevant_at_1 = any(kw in docs[0].get("content", "").lower() for kw in qdata.get("keywords", []))
                if relevant_at_1:
                    all_metrics["precision_at_1"] += 1.0

                relevant_at_3 = sum(
                    1 for d in docs[:3] if any(kw in d.get("content", "").lower() for kw in qdata.get("keywords", []))
                )
                all_metrics["precision_at_3"] += relevant_at_3 / min(3, len(docs))

        n = len(queries)
        for key in all_metrics:
            all_metrics[key] = round(all_metrics[key] / n, 4)

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

        return BenchmarkResult(
            config_name=self.config.name,
            metrics=all_metrics,
            avg_latency_ms=avg_latency,
            total_queries=n,
            config=asdict(self.config),
        )


DEFAULT_CONFIGS = [
    BenchmarkConfig(name="baseline", chunk_size=512, overlap=64, top_k=5, use_reranker=False),
    BenchmarkConfig(name="with_reranker", chunk_size=512, chunk_overlap=64, top_k=5, use_reranker=True),
    BenchmarkConfig(name="small_chunks", chunk_size=256, chunk_overlap=32, top_k=5, use_reranker=True),
    BenchmarkConfig(name="large_chunks", chunk_size=1024, chunk_overlap=128, top_k=5, use_reranker=True),
    BenchmarkConfig(name="high_recall", chunk_size=512, chunk_overlap=64, top_k=10, use_reranker=True, rerank_top_k=5),
    BenchmarkConfig(name="strict_threshold", chunk_size=512, chunk_overlap=64, top_k=10, use_reranker=True, score_threshold=0.3),
]


@click.command()
@click.option("--configs", default=None, help="JSON file with benchmark configurations")
@click.option("--output", default="benchmarks/results.json", help="Output file for results")
@click.option("--queries", default=None, help="JSON file with test queries")
def run_benchmark(configs: str | None, output: str, queries: str | None):
    """Run RAG benchmark across multiple configurations."""
    console.print("[bold cyan]CNI RAG - Benchmark Suite[/bold cyan]\n")

    # Load configs
    if configs:
        with open(configs, encoding="utf-8") as f:
            config_dicts = json.load(f)
        bench_configs = [BenchmarkConfig(**c) for c in config_dicts]
    else:
        bench_configs = DEFAULT_CONFIGS

    # Load queries
    if queries:
        with open(queries, encoding="utf-8") as f:
            test_queries = json.load(f)
    else:
        test_queries = TEST_QUERIES

    console.print(f"Configurations: {len(bench_configs)}")
    console.print(f"Test queries: {len(test_queries)}\n")

    results: list[BenchmarkResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        for bc in bench_configs:
            task = progress.add_task(f"[cyan]Testing: {bc.name}...", total=len(test_queries))
            bench = RAGBenchmark(bc)
            result = bench.evaluate(test_queries)
            results.append(result)
            progress.update(task, completed=len(test_queries))

    # Save results
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "config_name": r.config_name,
                    "metrics": r.metrics,
                    "avg_latency_ms": r.avg_latency_ms,
                    "total_queries": r.total_queries,
                    "config": r.config,
                }
                for r in results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Print results table
    table = Table(title="Benchmark Results", title_style="bold")
    table.add_column("Config", style="cyan")
    table.add_column("MRR", justify="right")
    table.add_column("R@1", justify="right")
    table.add_column("R@3", justify="right")
    table.add_column("R@5", justify="right")
    table.add_column("P@1", justify="right")
    table.add_column("P@3", justify="right")
    table.add_column("ClsAcc", justify="right")
    table.add_column("Latency (ms)", justify="right")

    for r in results:
        m = r.metrics
        table.add_row(
            r.config_name,
            f"{m['mrr']:.3f}",
            f"{m['recall_at_1']:.3f}",
            f"{m['recall_at_3']:.3f}",
            f"{m['recall_at_5']:.3f}",
            f"{m['precision_at_1']:.3f}",
            f"{m['precision_at_3']:.3f}",
            f"{m['classification_accuracy']:.3f}",
            f"{r.avg_latency_ms:.1f}",
        )

    console.print()
    console.print(table)
    console.print(f"\n[green]Results saved to: {output}[/green]")

    # Identify best config
    best = max(results, key=lambda r: r.metrics["mrr"])
    console.print(f"\n[bold green]Best config: {best.config_name}[/bold green] (MRR={best.metrics['mrr']:.3f})")


if __name__ == "__main__":
    run_benchmark()
