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
    def __init__(self):
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
        return self.client

    def delete_collection(self) -> None:
        self.client.delete_collection(self.collection_name)
        logger.info(f"Deleted collection: {self.collection_name}")
