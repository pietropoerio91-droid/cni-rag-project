import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.core.config_loader import ConfigLoader
from src.vectorstore.qdrant_client import QdrantClientManager

logger = logging.getLogger(__name__)


class VectorRetriever:
    def __init__(self, embedding_model: Embeddings):
        self.manager = QdrantClientManager()
        self.client = self.manager.get_client()
        self.collection_name = self.manager.collection_name
        self.embedding_model = embedding_model

        config = ConfigLoader.get_rag_config()
        ret_config = config.get("retrieval", {})
        self.top_k = ret_config.get("top_k", 5)
        self.score_threshold = ret_config.get("score_threshold", 0.5)

    def retrieve(self, query: str, top_k: int | None = None, filter_condition: dict | None = None) -> list[dict[str, Any]]:
        k = top_k or self.top_k
        query_vector = self.embedding_model.embed_query(query)

        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=k,
            score_threshold=self.score_threshold,
            query_filter=filter_condition,
        )

        results = []
        for scored_point in search_result:
            results.append({
                "content": scored_point.payload.get("content", ""),
                "source": scored_point.payload.get("source", ""),
                "title": scored_point.payload.get("title", ""),
                "score": scored_point.score,
                "chunk_index": scored_point.payload.get("chunk_index", 0),
                "category": scored_point.payload.get("category", ""),
            })

        logger.debug(f"Retrieved {len(results)} results for query (k={k})")
        return results

    def retrieve_by_category(self, query: str, category: str, top_k: int | None = None) -> list[dict[str, Any]]:
        from qdrant_client.http import models as rest

        filter_condition = rest.Filter(
            must=[rest.FieldCondition(key="category", match=rest.MatchValue(value=category))]
        )
        return self.retrieve(query, top_k=top_k, filter_condition=filter_condition)

    def hybrid_retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        return self.retrieve(query, top_k=top_k)
