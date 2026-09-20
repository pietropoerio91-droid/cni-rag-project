import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.core.config_loader import ConfigLoader
from src.rag.fusion import reciprocal_rank_fusion
from src.rag.query_classifier import QueryClassifier
from src.rag.sparse_index import BM25Index, carica_da_qdrant
from src.vectorstore.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Recupero a due canali: denso su Qdrant e lessicale BM25, fusi per rango.

    Con `retrieval.hybrid_search.enabled` a false il comportamento e' identico a
    quello della configurazione congelata del run FINAL_V2: solo ricerca densa,
    eventuale filtro di categoria, nessuna fusione. Questo serve a poter
    riprodurre la linea di base senza cambiare ramo.

    Con la bandiera attiva, i due canali interrogano entrambi l'intero corpus e
    le loro liste vengono fuse. Il numero di candidati passati al riordino resta
    `retrieval.top_k`: cambia *quali* documenti arrivano al cross-encoder, non
    *quanti*. E' una scelta voluta, perche' il cross-encoder e' lo stadio
    costoso su CPU e perche' cosi' il confronto con la linea di base resta
    pulito.
    """

    def __init__(self, embedding_model: Embeddings):
        self.vector_retriever = VectorRetriever(embedding_model)
        self.query_classifier = QueryClassifier()
        config = ConfigLoader.get_rag_config()
        retrieval = config.get("retrieval", {})

        self.top_k = retrieval.get("top_k", 25)
        self.hybrid_config = retrieval.get("hybrid_search", {})
        self.hybrid_enabled = self.hybrid_config.get("enabled", False)
        self.dense_top_k = self.hybrid_config.get("dense_top_k", 50)
        self.sparse_top_k = self.hybrid_config.get("sparse_top_k", 50)
        self.rrf_k = self.hybrid_config.get("rrf_k", 60)

        # Filtro rigido di categoria. Default True per retrocompatibilita', ma
        # la misura sull'indice mostra che le sei categorie non producibili dal
        # classificatore contengono il 75,8% dei chunk: ogni query classificata
        # perde quindi i tre quarti del corpus. L'ablation favorisce la
        # disattivazione su tutte le metriche (Hit@5 40,0% contro 33,3%),
        # pur senza raggiungere la significativita' statistica con n=30.
        self.category_filter = retrieval.get("category_filter", True)

        self._indice_lessicale: BM25Index | None = None

    # ------------------------------------------------------------------ #

    @property
    def indice_lessicale(self) -> BM25Index:
        """Costruito alla prima richiesta e poi riusato.

        I testi vengono letti dal payload di Qdrant: l'indice lessicale non
        richiede ne' un nuovo crawling ne' una reindicizzazione, e si ricostruisce
        in pochi secondi a ogni avvio del processo.
        """
        if self._indice_lessicale is None:
            manager = self.vector_retriever.manager
            documenti = carica_da_qdrant(manager.get_client(), manager.collection_name)
            bm25_config = self.hybrid_config.get("bm25", {})
            self._indice_lessicale = BM25Index(
                documenti,
                k1=bm25_config.get("k1", 1.2),
                b=bm25_config.get("b", 0.75),
                include_title=self.hybrid_config.get("include_title", True),
            )
        return self._indice_lessicale

    def _filtro_categoria(self, query: str):
        categoria = self.query_classifier.classify(query)
        if not self.category_filter or categoria == "generico":
            return None, categoria
        from qdrant_client.http import models as rest
        return rest.Filter(
            must=[rest.FieldCondition(key="category", match=rest.MatchValue(value=categoria))]
        ), categoria

    # ------------------------------------------------------------------ #

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        k = top_k or self.top_k
        filtro, categoria = self._filtro_categoria(query)

        if not self.hybrid_enabled:
            risultati = self.vector_retriever.retrieve(query, top_k=k, filter_condition=filtro)
            logger.info(
                f"Recupero denso: {len(risultati)} risultati "
                f"(categoria: {categoria}, filtro: {'attivo' if filtro else 'no'})"
            )
            return risultati

        # Pescata larga dai due canali: costa poco e da' alla fusione piu'
        # materiale fra cui scegliere. Il filtro di categoria, quando attivo,
        # resta applicato al solo canale denso, che e' quello su cui e' definito.
        densi = self.vector_retriever.retrieve(
            query, top_k=self.dense_top_k, filter_condition=filtro
        )
        lessicali = self.indice_lessicale.retrieve(query, top_k=self.sparse_top_k)

        fusi = reciprocal_rank_fusion([densi, lessicali], k=self.rrf_k, top_k=k)

        logger.info(
            f"Recupero ibrido: {len(densi)} densi + {len(lessicali)} lessicali "
            f"-> {len(fusi)} candidati (categoria: {categoria}, "
            f"filtro: {'attivo' if filtro else 'no'}, RRF k={self.rrf_k})"
        )
        return fusi
