import logging
from typing import Any

logger = logging.getLogger(__name__)


class CitationBuilder:
    def build(self, documents: list[dict[str, Any]], response: str) -> list[dict[str, Any]]:
        citations = []
        used_sources = set()

        for doc in documents:
            content = doc.get("content", "")
            source = doc.get("source", "")
            title = doc.get("title", "")

            if not source:
                continue

            citation = {
                "title": title or source.split("/")[-1],
                "source": source,
                "relevance_score": round(doc.get("score", 0), 4),
                "excerpt": self._extract_excerpt(content, 200),
            }

            source_key = source.split("/")[-1] if source else ""
            if source_key not in used_sources:
                used_sources.add(source_key)
                citations.append(citation)

        return citations

    @staticmethod
    def _extract_excerpt(text: str, max_length: int = 200) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length].rsplit(" ", 1)[0] + "..."
