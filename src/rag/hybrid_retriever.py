import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.core.config_loader import ConfigLoader
from src.rag.query_classifier import QueryClassifier
from src.vectorstore.bm25_sparse import DENSE_VECTOR, SPARSE_VECTOR, query_vector
from src.vectorstore.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Recupero ibrido: ricerca densa e BM25 nella stessa collection Qdrant, fuse con RRF.

    La collection ha due vettori per chunk, uno denso e uno sparso (BM25 con
    modificatore IDF), e si costruisce con `scripts/build_sparse_collection.py`.
    Una sola chiamata a Qdrant esegue i due `Prefetch` e la fusione per rango
    (Reciprocal Rank Fusion), che non richiede di normalizzare punteggi su scale
    diverse ne' di tarare pesi.

    Con `retrieval.hybrid_search.enabled` a false resta la sola ricerca densa,
    utile per misurare il contributo del canale lessicale.

    Il numero di candidati restituiti e' `retrieval.top_k`, anche con la fusione:
    il cross-encoder e' lo stadio costoso su CPU e cosi' la latenza non cambia.
    """

    def __init__(self, embedding_model: Embeddings):
        retrieval = ConfigLoader.get_rag_config().get("retrieval", {})
        hybrid = retrieval.get("hybrid_search", {})

        self.vector_retriever = VectorRetriever(embedding_model, vector_name=DENSE_VECTOR)
        self.query_classifier = QueryClassifier()

        self.top_k = retrieval.get("top_k", 25)
        self.hybrid_enabled = hybrid.get("enabled", False)
        self.dense_top_k = hybrid.get("dense_top_k", 50)
        self.sparse_top_k = hybrid.get("sparse_top_k", 50)
        self.rrf_k = hybrid.get("rrf_k", 60)

        # Filtro rigido di categoria. Default True per retrocompatibilita', ma
        # la misura sull'indice mostra che le sei categorie non producibili dal
        # classificatore contengono il 75,8% dei chunk: ogni query classificata
        # perde quindi i tre quarti del corpus. L'ablation favorisce la
        # disattivazione su tutte le metriche (Hit@5 40,0% contro 33,3%),
        # pur senza raggiungere la significativita' statistica con n=30.
        self.category_filter = retrieval.get("category_filter", True)

    def _category_filter(self, query: str):
        category = self.query_classifier.classify(query)
        if not self.category_filter or category == "generico":
            return None, category
        from qdrant_client.http import models as rest
        return rest.Filter(
            must=[rest.FieldCondition(key="category", match=rest.MatchValue(value=category))]
        ), category

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        k = top_k or self.top_k
        condition, category = self._category_filter(query)

        if not self.hybrid_enabled:
            results = self.vector_retriever.retrieve(query, top_k=k, filter_condition=condition)
            logger.info(
                f"Recupero denso: {len(results)} risultati "
                f"(categoria: {category}, filtro: {'attivo' if condition else 'no'})"
            )
            return results

        from qdrant_client.http import models as rest

        dense = self.vector_retriever
        points = dense.manager.get_client().query_points(
            collection_name=dense.collection_name,
            prefetch=[
                # Il filtro di categoria, quando attivo, riguarda il solo canale denso.
                rest.Prefetch(
                    query=dense.embedding_model.embed_query(query),
                    using=DENSE_VECTOR,
                    limit=self.dense_top_k,
                    score_threshold=dense.score_threshold,
                    filter=condition,
                ),
                rest.Prefetch(query=query_vector(query), using=SPARSE_VECTOR, limit=self.sparse_top_k),
            ],
            query=rest.RrfQuery(rrf=rest.Rrf(k=self.rrf_k)),
            limit=k,
            with_payload=True,
        ).points

        results = [
            {
                "content": p.payload.get("content", ""),
                "source": p.payload.get("source", ""),
                "title": p.payload.get("title", ""),
                "score": p.score,
                "chunk_index": p.payload.get("chunk_index", 0),
                "category": p.payload.get("category", ""),
            }
            for p in points
        ]
        logger.info(
            f"Recupero ibrido: {len(results)} candidati "
            f"(categoria: {category}, filtro: {'attivo' if condition else 'no'}, RRF k={self.rrf_k})"
        )
        return results
