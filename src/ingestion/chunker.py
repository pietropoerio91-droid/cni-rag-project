import logging
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class DocumentChunker:
    def __init__(self):
        config = ConfigLoader.get_rag_config()
        chunk_config = config.get("chunking", {})
        self.chunk_size = chunk_config.get("chunk_size", 512)
        self.chunk_overlap = chunk_config.get("chunk_overlap", 64)
        self.separators = chunk_config.get("separators", ["\n\n", "\n", ".", " ", ""])

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            length_function=len,
            keep_separator=False,
        )

    def chunk_document(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        content = document.get("content", "")
        url = document.get("url", "")
        title = document.get("title", "")
        meta = document.get("meta", {})

        if not content:
            return []

        if len(content) <= self.chunk_size:
            chunks = [content]
        else:
            chunks = self.splitter.split_text(content)
        chunk_docs: list[dict[str, Any]] = []

        for i, chunk_text in enumerate(chunks):
            chunk_doc = {
                "content": chunk_text,
                "metadata": {
                    **meta,
                    "source": url,
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            }
            chunk_docs.append(chunk_doc)

        logger.debug(f"Split document '{title}' into {len(chunks)} chunks")
        return chunk_docs

    def chunk_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        all_chunks: list[dict[str, Any]] = []
        for doc in documents:
            all_chunks.extend(self.chunk_document(doc))
        logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
        return all_chunks
