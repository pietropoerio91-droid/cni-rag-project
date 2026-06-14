import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.core.config_loader import ConfigLoader
from src.rag.query_classifier import QueryClassifier
from src.vectorstore.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, embedding_model: Embeddings):
        self.vector_retriever = VectorRetriever(embedding_model)
        self.query_classifier = QueryClassifier()
        config = ConfigLoader.get_rag_config()
        self.hybrid_config = config.get("retrieval", {}).get("hybrid_search", {})
        self.dense_weight = self.hybrid_config.get("dense_weight", 0.7)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        category = self.query_classifier.classify(query)
        filter_cond = None

        if category != "generico":
            from qdrant_client.http import models as rest
            filter_cond = rest.Filter(
                must=[rest.FieldCondition(key="category", match=rest.MatchValue(value=category))]
            )

        results = self.vector_retriever.retrieve(
            query=query,
            top_k=top_k,
            filter_condition=filter_cond,
        )

        logger.info(f"Hybrid retriever found {len(results)} results (category: {category})")
        return results
