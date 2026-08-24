import asyncio
import csv
import io
import json
import logging
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["TOKENIZERS_PARALLELISM"] = "false"

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import (
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    CitationResponse,
    RetrievedDocResponse,
)
from src.core.model_factory import ModelFactory
from src.rag.rag_chain import RAGChain
from src.vectorstore.indexer import VectorIndexer

logger = logging.getLogger(__name__)

router = APIRouter()

_rag_chain: RAGChain | None = None
_vector_indexer: VectorIndexer | None = None

_query_log: list[dict[str, Any]] = []
_MAX_QUERY_LOG = 500
_CSV_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "queries"
_CSV_DIR.mkdir(parents=True, exist_ok=True)
_feedback_store: dict[str, bool] = {}
_test_cache: dict[str, Any] | None = None
_TEST_QUESTIONS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "test_questions.json"

_ingest_status: dict[str, str | int | float | None] = {
    "running": False,
    "phase": "",
    "progress_pct": 0,
    "documents_found": 0,
    "documents_total": 0,
    "chunks_indexed": 0,
    "message": "",
    "started_at": None,
    "finished_at": None,
}


class IngestStatusResponse(BaseModel):
    running: bool
    phase: str
    progress_pct: float
    documents_found: int
    documents_total: int
    chunks_indexed: int
    message: str
    started_at: str | None = None
    finished_at: str | None = None


def get_rag_chain() -> RAGChain:
    global _rag_chain
    if _rag_chain is None:
        llm = ModelFactory.create_llm()
        embeddings = ModelFactory.create_embeddings()
        _rag_chain = RAGChain(llm=llm, embeddings=embeddings)
    return _rag_chain


def get_vector_indexer() -> VectorIndexer:
    global _vector_indexer
    if _vector_indexer is None:
        _vector_indexer = VectorIndexer()
    return _vector_indexer


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    try:
        chain = get_rag_chain()
        t0 = time.perf_counter()
        result = chain.query(request.question)
        latency = round((time.perf_counter() - t0) * 1000, 1)

        doc_count = len(result.get("citations", []))
        top_score = round(result["citations"][0]["relevance_score"], 4) if result.get("citations") else 0

        citation_scores = [round(c["relevance_score"], 4) for c in result.get("citations", [])]
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "question": request.question[:120],
            "category": result["category"],
            "doc_count": doc_count,
            "top_score": top_score,
            "citation_scores": citation_scores,
            "latency_ms": latency,
            "response_length": len(result["response"]),
        }
        _query_log.append(log_entry)
        if len(_query_log) > _MAX_QUERY_LOG:
            _query_log.pop(0)

        csv_path = _CSV_DIR / f"query_log_{datetime.now().strftime('%Y-%m-%d')}.csv"
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(log_entry.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in log_entry.items()})

        return QueryResponse(
            response=result["response"],
            citations=[CitationResponse(**c) for c in result["citations"]],
            category=result["category"],
            trace_id=result["trace_id"],
            fallback_triggered=result.get("fallback_triggered", False),
            retrieved_docs=[RetrievedDocResponse(**d) for d in result.get("retrieved_docs", [])],
            context_docs=[RetrievedDocResponse(**d) for d in result.get("reranked_docs", [])],
        )
    except Exception as e:
        import traceback
        logger.error(f"Query error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query/log")
async def query_log():
    return _query_log[-50:]


@router.get("/query/export")
async def query_export():
    today = datetime.now().strftime("%Y-%m-%d")
    csv_path = _CSV_DIR / f"query_log_{today}.csv"
    if csv_path.exists():
        return StreamingResponse(
            io.open(csv_path, "r", encoding="utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=query_log_{today}.csv"},
        )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["timestamp", "question", "category", "doc_count", "top_score", "latency_ms", "response_length"])
    writer.writeheader()
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=query_log_{today}.csv"},
    )


@router.get("/query/stats")
async def query_stats():
    if not _query_log:
        return {
            "total_queries": 0,
            "avg_docs_retrieved": 0,
            "avg_top_score": 0,
            "avg_latency_ms": 0,
            "category_distribution": {},
            "recent": [],
        }

    doc_counts = [q["doc_count"] for q in _query_log]
    top_scores = [q["top_score"] for q in _query_log if q["top_score"] > 0]
    latencies = [q["latency_ms"] for q in _query_log]
    categories = Counter(q["category"] for q in _query_log)

    return {
        "total_queries": len(_query_log),
        "avg_docs_retrieved": round(sum(doc_counts) / len(doc_counts), 1),
        "avg_top_score": round(sum(top_scores) / len(top_scores), 4) if top_scores else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
        "category_distribution": dict(categories.most_common()),
        "recent": _query_log[-10:],
    }


_RELEVANCE_THRESHOLD = 0.3


@router.get("/query/metrics")
async def query_metrics():
    if not _query_log:
        return {
            "total_queries": 0,
            "mrr": 0,
            "recall_at_1": 0,
            "recall_at_3": 0,
            "recall_at_5": 0,
            "precision_at_1": 0,
            "precision_at_3": 0,
            "precision_at_5": 0,
            "system_cls_acc": None,
            "human_cls_acc": None,
            "avg_cls_acc": None,
            "test_total": 0,
        }

    mrr_values = []
    recall_at_1 = []
    recall_at_3 = []
    recall_at_5 = []
    precision_at_1 = []
    precision_at_3 = []
    precision_at_5 = []

    for q in _query_log:
        scores = q.get("citation_scores", [])
        if not scores:
            mrr_values.append(0)
            recall_at_1.append(0)
            recall_at_3.append(0)
            recall_at_5.append(0)
            precision_at_1.append(0)
            precision_at_3.append(0)
            precision_at_5.append(0)
            continue

        relevant = [s > _RELEVANCE_THRESHOLD for s in scores]

        rank_first = next((i + 1 for i, r in enumerate(relevant) if r), None)
        mrr_values.append(1.0 / rank_first if rank_first else 0)

        def top_k_relevant(k):
            return sum(relevant[:k])

        recall_at_1.append(top_k_relevant(1) / 1)
        recall_at_3.append(top_k_relevant(3) / 3)
        recall_at_5.append(top_k_relevant(min(5, len(scores))) / min(5, len(scores)))

        precision_at_1.append(top_k_relevant(1) / 1)
        precision_at_3.append(top_k_relevant(3) / 3)
        precision_at_5.append(top_k_relevant(min(5, len(scores))) / min(5, len(scores)))

    feedback_values = list(_feedback_store.values())
    human_cls_acc = round(sum(feedback_values) / len(feedback_values), 4) if feedback_values else None

    system_cls_acc = _test_cache["cls_acc"] if _test_cache else None

    avg_cls_acc = None
    if human_cls_acc is not None and system_cls_acc is not None:
        avg_cls_acc = round((human_cls_acc + system_cls_acc) / 2, 4)
    elif human_cls_acc is not None:
        avg_cls_acc = human_cls_acc
    elif system_cls_acc is not None:
        avg_cls_acc = system_cls_acc

    n = len(mrr_values)
    return {
        "total_queries": n,
        "mrr": round(sum(mrr_values) / n, 4),
        "recall_at_1": round(sum(recall_at_1) / n, 4),
        "recall_at_3": round(sum(recall_at_3) / n, 4),
        "recall_at_5": round(sum(recall_at_5) / n, 4),
        "precision_at_1": round(sum(precision_at_1) / n, 4),
        "precision_at_3": round(sum(precision_at_3) / n, 4),
        "precision_at_5": round(sum(precision_at_5) / n, 4),
        "system_cls_acc": system_cls_acc,
        "human_cls_acc": human_cls_acc,
        "avg_cls_acc": avg_cls_acc,
        "test_total": _test_cache["total"] if _test_cache else 0,
    }


class FeedbackRequest(BaseModel):
    trace_id: str
    category_correct: bool


@router.post("/query/feedback")
async def query_feedback(body: FeedbackRequest):
    _feedback_store[body.trace_id] = body.category_correct
    logger.info(f"Feedback per {body.trace_id}: {'corretta' if body.category_correct else 'sbagliata'}")
    return {"status": "ok"}


@router.post("/query/stream")
async def query_stream(request: QueryRequest):
    chain = get_rag_chain()

    async def event_generator():
        async for event in chain.astream(request.question):
            yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.post("/query/run-test")
async def query_run_test():
    global _test_cache
    chain = get_rag_chain()
    if not _TEST_QUESTIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="File test_questions.json non trovato")

    test_data = json.loads(_TEST_QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []
    correct = 0
    for item in test_data:
        try:
            result = chain.query(item["question"])
            predicted = result["category"]
            expected = item["expected_category"]
            is_correct = predicted == expected
            if is_correct:
                correct += 1
            results.append({
                "question": item["question"][:80],
                "expected": expected,
                "predicted": predicted,
                "correct": is_correct,
            })
        except Exception as e:
            logger.warning(f"Test question error: {item['question'][:40]} -> {e}")
            results.append({
                "question": item["question"][:80],
                "expected": item["expected_category"],
                "predicted": "error",
                "correct": False,
            })

    total = len(test_data)
    cls_acc = round(correct / total, 4) if total else 0
    _test_cache = {"cls_acc": cls_acc, "total": total, "correct": correct, "results": results}
    logger.info(f"Test completato: {correct}/{total} corrette (accuracy={cls_acc})")
    return _test_cache


@router.get("/health", response_model=HealthResponse)
async def health():
    try:
        indexer = get_vector_indexer()
        count = indexer.count_points()
        llm_connected = False
        try:
            import httpx
            r = httpx.get("http://localhost:11434/api/tags", timeout=5)
            llm_connected = r.status_code == 200
        except Exception:
            llm_connected = False
        return HealthResponse(
            status="ok",
            version="0.1.0",
            documents_indexed=count,
            llm_connected=llm_connected,
        )
    except Exception as e:
        return HealthResponse(
            status="error",
            version="0.1.0",
            documents_indexed=0,
            llm_connected=False,
        )


@router.get("/benchmark")
async def benchmark():
    results_dir = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "results"
    index_path = results_dir / "index.json"
    latest_path = results_dir / "latest.json"

    if not index_path.exists() or not latest_path.exists():
        return {
            "available": False,
            "message": "Nessun benchmark eseguito. Lancia: python benchmarks/run_benchmark.py",
            "runs": [],
            "latest": None,
            "best_overall": None,
        }

    index: list[dict] = json.loads(index_path.read_text())
    latest_data = json.loads(latest_path.read_text()) if latest_path.exists() else None

    best_overall = None
    if index:
        best_run = max(index, key=lambda r: r["best_mrr"])
        best_file = results_dir / best_run["file"]
        if best_file.exists():
            best_data = json.loads(best_file.read_text())
            best_overall = {
                "run_date": best_run["run_date"],
                "timestamp": best_run["timestamp"],
                "best_config": best_run["best_config"],
                "best_mrr": best_run["best_mrr"],
                "results": best_data["results"],
            }

    return {
        "available": True,
        "runs": sorted(index, key=lambda r: r["timestamp"], reverse=True),
        "latest": latest_data,
        "best_overall": best_overall,
    }


@router.get("/benchmark/runs/{timestamp}")
async def benchmark_run(timestamp: str):
    results_dir = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "results"
    run_file = results_dir / f"results_{timestamp}.json"
    if not run_file.exists():
        raise HTTPException(status_code=404, detail="Run non trovato")
    data = json.loads(run_file.read_text())
    return data


@router.get("/ingest/status", response_model=IngestStatusResponse)
async def ingest_status():
    return IngestStatusResponse(
        running=_ingest_status.get("running", False),
        phase=_ingest_status.get("phase", ""),
        progress_pct=_ingest_status.get("progress_pct", 0),
        documents_found=_ingest_status.get("documents_found", 0),
        documents_total=_ingest_status.get("documents_total", 0),
        chunks_indexed=_ingest_status.get("chunks_indexed", 0),
        message=_ingest_status.get("message", ""),
        started_at=str(_ingest_status.get("started_at")) if _ingest_status.get("started_at") else None,
        finished_at=str(_ingest_status.get("finished_at")) if _ingest_status.get("finished_at") else None,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest():
    if _ingest_status.get("running"):
        raise HTTPException(status_code=409, detail="Indicizzazione già in corso")

    async def _run_ingest():
        from src.ingestion.chunker import DocumentChunker
        from src.ingestion.cleaner import TextCleaner
        from src.ingestion.crawler import CNICrawler
        from src.ingestion.downloader import Downloader
        from src.ingestion.embedder import EmbeddingGenerator
        from src.ingestion.parser import DocumentParser
        from src.governance.public_data_filter import PublicDataFilter
        from src.governance.quality_check import QualityChecker

        try:
            _ingest_status.update({"running": True, "phase": "init", "progress_pct": 0, "message": "Avvio indicizzazione...", "started_at": datetime.now(), "documents_found": 0})

            crawler = CNICrawler()
            cleaner = TextCleaner()
            parser = DocumentParser()
            chunker = DocumentChunker()
            embedder = EmbeddingGenerator()
            downloader = Downloader()
            public_filter = PublicDataFilter()
            quality = QualityChecker()
            indexer = get_vector_indexer()

            _ingest_status.update({"phase": "clear", "message": "Pulisco indice esistente..."})
            indexer.clear_index()

            _ingest_status.update({"phase": "crawl", "message": "Scarico documenti da cni.it..."})
            new_docs = await crawler.crawl()
            _ingest_status.update({"documents_found": len(new_docs), "progress_pct": 20})

            existing_docs = downloader.load_documents()
            seen_urls = {doc.get("url", "") for doc in existing_docs if doc.get("url")}
            for doc in new_docs:
                url = doc.get("url", "")
                if url and url not in seen_urls:
                    existing_docs.append(doc)
                    seen_urls.add(url)
            _ingest_status.update({"documents_total": len(existing_docs), "progress_pct": 30})

            _ingest_status.update({"phase": "filter", "message": "Filtro e pulisco documenti..."})
            processed_docs = []
            for i, doc in enumerate(existing_docs):
                if not public_filter.is_public(doc.get("url", ""), doc.get("content", "")):
                    continue
                ok, _ = quality.check(doc.get("content", ""))
                if not ok:
                    continue
                cleaned = cleaner.clean(doc.get("content", ""))
                doc["content"] = cleaned
                doc["meta"]["category"] = public_filter.categorize(doc.get("url", ""), cleaned)
                processed_docs.append(doc)
                if i % 100 == 0:
                    _ingest_status.update({"documents_found": len(processed_docs)})
            _ingest_status.update({"documents_found": len(processed_docs), "progress_pct": 50})

            _ingest_status.update({"phase": "save", "message": "Salvo documenti..."})
            downloader.save_documents(processed_docs)
            _ingest_status.update({"progress_pct": 55})

            _ingest_status.update({"phase": "chunk", "message": "Creo chunk..."})
            chunks = chunker.chunk_documents(processed_docs)
            _ingest_status.update({"progress_pct": 65})

            _ingest_status.update({"phase": "embed", "message": "Genero embeddings..."})
            chunks_with_embeddings = embedder.process_chunks(chunks)
            _ingest_status.update({"progress_pct": 85})

            _ingest_status.update({"phase": "index", "message": "Indicizzo in Qdrant..."})
            indexed_count = indexer.index_chunks(chunks_with_embeddings)
            _ingest_status.update({"chunks_indexed": indexed_count, "progress_pct": 100})

            _ingest_status.update({
                "running": False,
                "phase": "done",
                "message": f"Indicizzazione completata: {indexed_count} chunk indicizzati",
                "finished_at": datetime.now(),
            })
        except Exception as e:
            logger.error(f"Ingest error: {e}")
            _ingest_status.update({
                "running": False,
                "phase": "error",
                "message": f"Errore: {e}",
                "finished_at": datetime.now(),
            })

    asyncio.create_task(_run_ingest())

    return IngestResponse(
        status="started",
        documents_crawled=0,
        documents_total=0,
        chunks_indexed=0,
        message="Indicizzazione avviata in background",
    )
