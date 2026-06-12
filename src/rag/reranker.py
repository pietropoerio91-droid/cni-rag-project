import logging
from typing import Any

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self):
        config = ConfigLoader.get_rag_config()
        rerank_config = config.get("reranking", {})
        self.enabled = rerank_config.get("enabled", True)
        self.top_k = rerank_config.get("top_k", 3)
        self.model_name = rerank_config.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Loaded reranker model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed to load reranker model: {e}. Using score-based reranking.")
                self.enabled = False

    def rerank(self, query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not results:
            return results

        if not self.enabled:
            return results[:self.top_k]

        self._load_model()

        if self._model is None:
            return sorted(results, key=lambda r: r.get("score", 0), reverse=True)[:self.top_k]

        pairs = [(query, r["content"]) for r in results]
        scores = self._model.predict(pairs)

        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)

        reranked = sorted(results, key=lambda r: r.get("rerank_score", 0), reverse=True)
        logger.debug(f"Reranked {len(results)} results, keeping top {self.top_k}")
        return reranked[:self.top_k]
