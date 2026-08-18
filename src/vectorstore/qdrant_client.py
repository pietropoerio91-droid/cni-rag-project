import logging
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    CollectionStatus,
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    VectorParams,
)

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class QdrantClientManager:
    _instance: "QdrantClientManager | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._init_client()

    def _init_client(self):
        self._initialized = True
        config = ConfigLoader.get_qdrant_config()
        qdrant_config = config.get("qdrant", {})
        self.mode = qdrant_config.get("mode", "local")
        self.collection_name = qdrant_config.get("collection_name", "cni_documents")
        self.vector_size = qdrant_config.get("vectors", {}).get("size", 384)

        if self.mode == "local":
            db_path = qdrant_config.get("path", "./data/qdrant_db")
            Path(db_path).mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=db_path)
            logger.info(f"Qdrant local mode at: {db_path}")
        else:
            host = qdrant_config.get("host", "localhost")
            port = qdrant_config.get("port", 6333)
            self.client = QdrantClient(host=host, port=port, prefer_grpc=False)
            logger.info(f"Qdrant connected to {host}:{port} (HTTP mode)")

        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            config = ConfigLoader.get_qdrant_config()
            qdrant_config = config.get("qdrant", {})
            vectors_config = qdrant_config.get("vectors", {})
            opts_config = qdrant_config.get("optimizers", {})

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vectors_config.get("size", 384),
                    distance=Distance[vectors_config.get("distance", "Cosine").upper()],
                    on_disk=qdrant_config.get("on_disk", False),
                ),
                optimizers_config=OptimizersConfigDiff(
                    default_segment_number=opts_config.get("default_segment_number", 2),
                    memmap_threshold=opts_config.get("memmap_threshold", 20000),
                ),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            )
            logger.info(f"Created collection: {self.collection_name}")
        else:
            logger.info(f"Collection '{self.collection_name}' already exists")

    def get_client(self) -> QdrantClient:
        if self._is_closed():
            logger.warning("Qdrant client is closed, reinitializing...")
            self._initialized = False
            self._init_client()
        return self.client

    def _is_closed(self) -> bool:
        if self.mode != "local":
            return False
        inner = getattr(self.client, "_client", None)
        try:
            return bool(inner and getattr(inner, "closed", False))
        except Exception:
            return False

    def delete_collection(self) -> None:
        self.client.delete_collection(self.collection_name)
        logger.info(f"Deleted collection: {self.collection_name}")

    def reinitialize(self) -> None:
        if self._is_closed():
            self._initialized = False
            self._init_client()
            return
        self.client.close()
        self._initialized = False
        self._init_client()
