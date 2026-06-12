import json
import logging
import os

from fastapi import APIRouter, HTTPException
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
        logger.error(f"Query error: {e}")
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
        llm_connected = True
        try:
            llm = ModelFactory.create_llm()
            llm.invoke("test")
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


@router.post("/ingest", response_model=IngestResponse)
async def ingest():
    from src.ingestion.crawler import CNICrawler
    from src.ingestion.cleaner import TextCleaner
    from src.ingestion.chunker import DocumentChunker
    from src.ingestion.downloader import Downloader
    from src.ingestion.embedder import EmbeddingGenerator
    from src.ingestion.parser import DocumentParser
    from src.governance.public_data_filter import PublicDataFilter
    from src.governance.quality_check import QualityChecker

    try:
        crawler = CNICrawler()
        cleaner = TextCleaner()
        parser = DocumentParser()
        chunker = DocumentChunker()
        embedder = EmbeddingGenerator()
        indexer = get_vector_indexer()
        downloader = Downloader()
        public_filter = PublicDataFilter()
        quality = QualityChecker()

        import asyncio

        raw_docs = await crawler.crawl()

        processed_docs = []
        for doc in raw_docs:
            if not public_filter.is_public(doc.get("url", ""), doc.get("content", "")):
                continue
            ok, _ = quality.check(doc.get("content", ""))
            if not ok:
                continue
            cleaned = cleaner.clean(doc.get("content", ""))
            doc["content"] = cleaned
            doc["meta"]["category"] = public_filter.categorize(doc.get("url", ""), cleaned)
            processed_docs.append(doc)

        downloader.save_documents(processed_docs)

        chunks = chunker.chunk_documents(processed_docs)
        chunks_with_embeddings = embedder.process_chunks(chunks)
        indexed_count = indexer.index_chunks(chunks_with_embeddings)

        return IngestResponse(
            status="success",
            documents_crawled=len(processed_docs),
            chunks_indexed=indexed_count,
            message=f"Crawled {len(processed_docs)} documents, indexed {indexed_count} chunks",
        )
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
