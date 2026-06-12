import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
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

    @app.on_event("startup")
    async def startup():
        logger.info("CNI RAG API starting up...")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("CNI RAG API shutting down...")

    return app


app = create_app()
