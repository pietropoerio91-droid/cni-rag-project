import logging
import uuid
from typing import Any

from qdrant_client.http.models import PointStruct

from src.core.config_loader import ConfigLoader
from src.vectorstore.bm25_sparse import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    average_length,
    document_vector,
    indexed_text,
    tokenize,
)
from src.vectorstore.qdrant_client import QdrantClientManager

logger = logging.getLogger(__name__)


UPSERT_BATCH_SIZE = 256  # come scripts/build_sparse_collection.py


class VectorIndexer:
    def __init__(self, collection_name: str | None = None):
        """`collection_name` scrive su una collection diversa da quella di
        produzione (creata se manca); None usa quella del qdrant_config.yaml."""
        self.manager = QdrantClientManager()
        self._collection_name = collection_name
        if collection_name:
            self.manager.ensure_collection(collection_name)

    @property
    def collection_name(self) -> str:
        # Senza nome esplicito segue la collection attiva, anche dopo un cambio.
        return self._collection_name or self.manager.collection_name

    @collection_name.setter
    def collection_name(self, name: str) -> None:
        self._collection_name = name

    def _get_client(self):
        return self.manager.get_client()

    def index_chunks(self, chunks: list[dict[str, Any]], batch_size: int = UPSERT_BATCH_SIZE) -> int:
        """Indicizza i chunk con vettore denso e vettore sparso BM25.

        La lunghezza media dei documenti (`avgdl`) entra nei pesi BM25 ed e'
        calcolata sui chunk ricevuti: l'indicizzazione va quindi fatta in una sola
        chiamata sull'intero corpus (come fanno gli script di ingestione). Chi
        aggiunge chunk a una collection esistente usa la lunghezza media del
        proprio lotto: per averne una coerente si ricostruisce la collection.

        L'invio a Qdrant avviene invece a lotti di `batch_size` punti: `avgdl` e'
        gia' calcolata sull'intero corpus, quindi i pesi non dipendono dai lotti,
        e si evita di costruire e spedire l'intero corpus in un'unica richiesta.
        """
        client = self._get_client()
        bm25 = ConfigLoader.get_rag_config().get("retrieval", {}).get("hybrid_search", {}).get("bm25", {})
        k1, b, include_title = bm25.get("k1", 1.2), bm25.get("b", 0.75), bm25.get("include_title", True)

        valid = []
        for chunk in chunks:
            if not chunk.get("embedding"):
                logger.warning("Skipping chunk without embedding")
                continue
            valid.append(chunk)

        payloads = []
        for chunk in valid:
            metadata = chunk.get("metadata", {})
            payload = {
                "content": chunk.get("content", ""),
                "source": metadata.get("source", ""),
                "title": metadata.get("title", ""),
                "chunk_index": metadata.get("chunk_index", 0),
                "total_chunks": metadata.get("total_chunks", 0),
            }
            if metadata.get("category", ""):
                payload["category"] = metadata["category"]
            payloads.append(payload)

        tokens = [tokenize(indexed_text(p, include_title)) for p in payloads]
        avgdl = average_length(tokens)

        indexed = 0
        for start in range(0, len(valid), batch_size):
            end = start + batch_size
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        DENSE_VECTOR: chunk["embedding"],
                        SPARSE_VECTOR: document_vector(tk, avgdl, k1, b),
                    },
                    payload=payload,
                )
                for chunk, payload, tk in zip(valid[start:end], payloads[start:end], tokens[start:end])
            ]
            client.upsert(collection_name=self.collection_name, points=points)
            indexed += len(points)
            logger.info(f"Indexed {indexed}/{len(valid)} points into '{self.collection_name}'")

        if indexed:
            logger.info(f"Indexed {indexed} points into '{self.collection_name}' (avgdl={avgdl:.1f})")
        else:
            logger.warning("No points to index")

        return indexed

    def count_points(self) -> int:
        collection_info = self._get_client().get_collection(self.collection_name)
        return collection_info.points_count

    def close(self) -> None:
        self.manager.client.close()
        self.manager._initialized = False
        logger.info("Qdrant client closed")

    def clear_index(self) -> None:
        self.manager.delete_collection(self.collection_name)
        self.manager.reinitialize()
        self.manager.ensure_collection(self.collection_name)
        logger.info(f"Index '{self.collection_name}' cleared and recreated")
