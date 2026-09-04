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
        retrieval = config.get("retrieval", {})
        self.hybrid_config = retrieval.get("hybrid_search", {})
        self.dense_weight = self.hybrid_config.get("dense_weight", 0.7)

        # Filtro rigido di categoria. Default True per retrocompatibilita', ma
        # la misura sull'indice mostra che le sei categorie non producibili dal
        # classificatore contengono il 75,8% dei chunk: ogni query classificata
        # perde quindi i tre quarti del corpus. L'ablation favorisce la
        # disattivazione su tutte le metriche (Hit@5 40,0% contro 33,3%),
        # pur senza raggiungere la significativita' statistica con n=30.
        self.category_filter = retrieval.get("category_filter", True)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        category = self.query_classifier.classify(query)
        filter_cond = None

        if self.category_filter and category != "generico":
            from qdrant_client.http import models as rest
            filter_cond = rest.Filter(
                must=[rest.FieldCondition(key="category", match=rest.MatchValue(value=category))]
            )

        results = self.vector_retriever.retrieve(
            query=query,
            top_k=top_k,
            filter_condition=filter_cond,
        )

        logger.info(f"Hybrid retriever found {len(results)} results "
                    f"(category: {category}, filtro: {'attivo' if filter_cond else 'no'})")
        return results
