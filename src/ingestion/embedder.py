import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.core.model_factory import ModelFactory

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    def __init__(self, embedding_model: Embeddings | None = None):
        self.model = embedding_model or ModelFactory.create_embeddings()

    def generate(self, text: str) -> list[float]:
        return self.model.embed_query(text)

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        return self.model.embed_documents(texts)

    def process_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        texts = [chunk["content"] for chunk in chunks]
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = self.generate_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        logger.info(f"Embeddings generated for {len(chunks)} chunks")
        return chunks
