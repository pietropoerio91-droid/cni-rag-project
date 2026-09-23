import logging
import re
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, HnswConfigDiff, OptimizersConfigDiff

from src.core.config_loader import ConfigLoader
from src.vectorstore.bm25_sparse import DENSE_VECTOR, SPARSE_VECTOR, collection_schema

logger = logging.getLogger(__name__)

QDRANT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "qdrant_config.yaml"


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

    def describe_collection(self, name: str) -> dict:
        """Numero di punti e compatibilita' della collection con il retriever attuale.

        Compatibile = ha il vettore denso della dimensione configurata (quella del
        modello di embedding in uso) e il vettore sparso BM25 del recupero ibrido.
        """
        params = self.client.get_collection(name).config.params
        vectors = params.vectors if isinstance(params.vectors, dict) else {}
        dense = vectors.get(DENSE_VECTOR)
        dense_size = dense.size if dense else None
        hybrid = SPARSE_VECTOR in (params.sparse_vectors or {})
        expected = ConfigLoader.get_qdrant_config().get("qdrant", {}).get("vectors", {}).get("size", 384)

        motivo = None
        if dense_size is None:
            motivo = f"manca il vettore denso '{DENSE_VECTOR}' (formato precedente al recupero ibrido)"
        elif dense_size != expected:
            motivo = f"vettori da {dense_size} dimensioni, il modello di embedding in uso ne produce {expected}"
        elif not hybrid:
            motivo = f"manca il vettore sparso '{SPARSE_VECTOR}' del BM25"

        return {
            "name": name,
            "points": self.client.count(name).count,
            "dense_size": dense_size,
            "hybrid": hybrid,
            "compatible": motivo is None,
            "incompatible_reason": motivo,
            "active": name == self.collection_name,
        }

    def list_collections(self) -> list[dict]:
        names = sorted(c.name for c in self.get_client().get_collections().collections)
        return [self.describe_collection(n) for n in names]

    def set_active_collection(self, name: str) -> dict:
        """Rende `name` la collection usata da chat, dashboard e valutazioni.

        Il cambio si scrive in config/qdrant_config.yaml: il file resta l'unica
        fonte della configurazione e un riavvio dell'API riparte dalla stessa
        collection. Si rifiuta una collection inesistente o incompatibile.
        """
        client = self.get_client()
        if not any(c.name == name for c in client.get_collections().collections):
            raise ValueError(f"La collection '{name}' non esiste")
        info = self.describe_collection(name)
        if not info["compatible"]:
            raise ValueError(f"La collection '{name}' non e' utilizzabile: {info['incompatible_reason']}")

        previous = self.collection_name
        _write_collection_name(name)
        ConfigLoader.get_qdrant_config().setdefault("qdrant", {})["collection_name"] = name
        self.collection_name = name
        logger.info(f"Collection attiva: '{previous}' -> '{name}'")
        return {**info, "active": True, "previous": previous}

    def delete_collection(self, name: str | None = None) -> None:
        name = name or self.collection_name
        if self.mode == "local":
            # Qdrant locale cancella la cartella della collection senza chiuderne il
            # file SQLite. Su Windows un file aperto non si cancella (l'errore e'
            # ignorato) e la collection ricreata con lo stesso nome riapre i vecchi
            # punti: la si chiude prima, esplicitamente.
            local = getattr(self.client, "_client", None)
            collection = getattr(local, "collections", {}).get(name)
            if collection is not None:
                collection.close()
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


def _write_collection_name(name: str, path: Path | None = None) -> None:
    """Riscrive solo la riga `collection_name:` del YAML, lasciando intatti i commenti."""
    path = path or QDRANT_CONFIG_PATH
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r"(?m)^(\s*collection_name:\s*).*$", lambda m: m.group(1) + name, text, count=1)
    if n != 1:
        raise ValueError(f"Riga 'collection_name:' non trovata in {path}")
    path.write_text(new, encoding="utf-8")
