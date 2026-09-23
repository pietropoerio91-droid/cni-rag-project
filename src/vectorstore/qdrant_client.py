import logging
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, HnswConfigDiff, OptimizersConfigDiff

from src.core.config_loader import ConfigLoader
from src.vectorstore.bm25_sparse import collection_schema

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

        self.ensure_collection(self.collection_name)

    def ensure_collection(self, name: str) -> None:
        """Crea la collection `name` con lo schema del progetto, se non esiste."""
        collections = self.client.get_collections().collections
        exists = any(c.name == name for c in collections)

        if not exists:
            config = ConfigLoader.get_qdrant_config()
            qdrant_config = config.get("qdrant", {})
            vectors_config = qdrant_config.get("vectors", {})
            opts_config = qdrant_config.get("optimizers", {})

            self.client.create_collection(
                collection_name=name,
                **collection_schema(
                    dense_size=vectors_config.get("size", 384),
                    distance=Distance[vectors_config.get("distance", "Cosine").upper()],
                    on_disk=qdrant_config.get("on_disk", False),
                ),
                optimizers_config=OptimizersConfigDiff(
                    default_segment_number=opts_config.get("default_segment_number", 2),
                    memmap_threshold=opts_config.get("memmap_threshold", 20000),
                ),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            )
            logger.info(f"Created collection: {name}")
        else:
            logger.info(f"Collection '{name}' already exists")

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

    def delete_collection(self, name: str | None = None) -> None:
        name = name or self.collection_name
        self.client.delete_collection(name)
        logger.info(f"Deleted collection: {name}")

    def reinitialize(self) -> None:
        if self._is_closed():
            self._initialized = False
            self._init_client()
            return
        self.client.close()
        self._initialized = False
        self._init_client()
