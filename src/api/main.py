import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.api.qdrant_browser import router as qdrant_router
from src.api.routes import router, get_rag_chain
from src.core.logging import setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()

    origins = os.getenv("API_CORS_ORIGINS", "http://localhost:4200").split(",")

    app = FastAPI(
        title="CNI RAG API",
        description="API per l'estrazione e consultazione intelligente dei dati pubblici del CNI",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")
    app.include_router(qdrant_router, prefix="/api/v1")

    html_path = Path(__file__).resolve().parent / "qdrant_browser.html"

    @app.get("/qdrant", response_class=HTMLResponse)
    async def qdrant_browser():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.on_event("startup")
    async def startup():
        logger.info("CNI RAG API starting up...")
        logger.info("Pre-loading RAG chain...")
        try:
            chain = get_rag_chain()
            logger.info("RAG chain loaded: %s", type(chain).__name__)
        except Exception as e:
            logger.error("Failed to load models: %s", e)

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("CNI RAG API shutting down...")

    return app


app = create_app()
