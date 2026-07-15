import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import (
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    CitationResponse,
)
from src.core.model_factory import ModelFactory
from src.rag.rag_chain import RAGChain
from src.vectorstore.indexer import VectorIndexer

logger = logging.getLogger(__name__)

router = APIRouter()

_rag_chain: RAGChain | None = None
_vector_indexer: VectorIndexer | None = None

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
        result = chain.query(request.question)
        return QueryResponse(
            response=result["response"],
            citations=[CitationResponse(**c) for c in result["citations"]],
            category=result["category"],
            trace_id=result["trace_id"],
        )
    except Exception as e:
        import traceback
        logger.error(f"Query error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def query_stream(request: QueryRequest):
    chain = get_rag_chain()

    async def event_generator():
        async for event in chain.astream(request.question):
            yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


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
    path = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "results.json"
    if not path.exists():
        return {
            "available": False,
            "message": "Nessun benchmark eseguito. Lancia: python benchmarks/run_benchmark.py",
            "results": [],
            "best_config": None,
        }
    data = json.loads(path.read_text())
    best = max(data, key=lambda r: r["metrics"]["mrr"]) if data else None
    return {"available": True, "results": data, "best_config": best}


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
