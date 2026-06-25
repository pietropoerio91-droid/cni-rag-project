import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from qdrant_client import QdrantClient

from src.vectorstore.qdrant_client import QdrantClientManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qdrant", tags=["qdrant"])

_qdrant_manager: QdrantClientManager | None = None


def get_qdrant_manager() -> QdrantClientManager:
    global _qdrant_manager
    if _qdrant_manager is None:
        _qdrant_manager = QdrantClientManager()
    return _qdrant_manager


@router.get("", response_class=HTMLResponse)
async def qdrant_browse_page():
    html = Path(__file__).resolve().parent / "qdrant_browser.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))


@router.get("/stats")
async def qdrant_stats(mgr: QdrantClientManager = Depends(get_qdrant_manager)):
    client = mgr.get_client()
    info = client.get_collection(mgr.collection_name)
    return {
        "collection": mgr.collection_name,
        "mode": mgr.mode,
        "points_count": info.points_count,
        "vectors_count": info.vectors_count,
    }


@router.get("/documents")
async def qdrant_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    mgr: QdrantClientManager = Depends(get_qdrant_manager),
):
    client = mgr.get_client()

    if search:
        from src.core.model_factory import ModelFactory
        embedder = ModelFactory.create_embeddings()
        vector = embedder.embed_query(search)
        results = client.query_points(
            collection_name=mgr.collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        docs = []
        for pt in results.points:
            d = {"id": pt.id, "score": round(pt.score, 4)}
            d.update({k: v for k, v in pt.payload.items() if k != "content"})
            d["content"] = pt.payload.get("content", "")[:500]
            docs.append(d)
        return {"documents": docs, "total": len(docs), "search": search}
    else:
        points, next_offset = client.scroll(
            collection_name=mgr.collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
        )
        docs = []
        for pt in points:
            d = {"id": pt.id, "score": getattr(pt, "score", 0)}
            payload = pt.payload or {}
            for k, v in payload.items():
                if k == "content":
                    d["content"] = v[:500]
                else:
                    d[k] = v
            docs.append(d)
        return {"documents": docs, "offset": next_offset or 0, "total": None}


@router.get("/documents/{point_id}")
async def qdrant_document_detail(point_id: str, mgr: QdrantClientManager = Depends(get_qdrant_manager)):
    client = mgr.get_client()
    points = client.retrieve(
        collection_name=mgr.collection_name,
        ids=[point_id],
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Document not found")
    pt = points[0]
    payload = pt.payload or {}
    return {
        "id": pt.id,
        "score": getattr(pt, "score", 0),
        "version": getattr(pt, "version", 0),
        **{k: v for k, v in payload.items()},
    }
