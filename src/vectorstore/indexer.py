import logging
import uuid
from typing import Any

from qdrant_client.http.models import PointStruct

from src.vectorstore.qdrant_client import QdrantClientManager

logger = logging.getLogger(__name__)


class VectorIndexer:
    def __init__(self):
        self.manager = QdrantClientManager()
        self.client = self.manager.get_client()
        self.collection_name = self.manager.collection_name

    def index_chunks(self, chunks: list[dict[str, Any]]) -> int:
        points = []
        for chunk in chunks:
            embedding = chunk.get("embedding")
            if not embedding:
                logger.warning("Skipping chunk without embedding")
                continue

            point_id = str(uuid.uuid4())
            payload = {
                "content": chunk.get("content", ""),
                "source": chunk.get("metadata", {}).get("source", ""),
                "title": chunk.get("metadata", {}).get("title", ""),
                "chunk_index": chunk.get("metadata", {}).get("chunk_index", 0),
                "total_chunks": chunk.get("metadata", {}).get("total_chunks", 0),
            }
            category = chunk.get("metadata", {}).get("category", "")
            if category:
                payload["category"] = category

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))

        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info(f"Indexed {len(points)} points into '{self.collection_name}'")
        else:
            logger.warning("No points to index")

        return len(points)

    def count_points(self) -> int:
        collection_info = self.client.get_collection(self.collection_name)
        return collection_info.points_count

    def clear_index(self) -> None:
        self.manager.delete_collection()
        self.manager = QdrantClientManager()
        self.client = self.manager.get_client()
        logger.info("Index cleared and recreated")
