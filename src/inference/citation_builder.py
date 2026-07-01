import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class CitationBuilder:
    def build(self, documents: list[dict[str, Any]], response: str) -> list[dict[str, Any]]:
        citations = []
        used_sources = set()
        response_lower = response.lower()
        response_words = set(re.findall(r"\w{4,}", response_lower))

        for doc in documents:
            content = doc.get("content", "")
            source = doc.get("source", "")
            title = doc.get("title", "")

            if not source:
                continue

            content_lower = content.lower()
            content_words = set(re.findall(r"\w{4,}", content_lower))
            overlap = len(content_words & response_words) / max(len(content_words | response_words), 1)
            has_relevance = overlap > 0.05

            citation = {
                "title": title or source.split("/")[-1],
                "source": source,
                "relevance_score": round(doc.get("score", 0), 4),
                "excerpt": self._extract_excerpt(content, 200),
                "content_overlap": round(overlap, 3),
            }

            source_key = source.split("/")[-1] if source else ""
            if source_key not in used_sources and has_relevance:
                used_sources.add(source_key)
                citations.append(citation)

        if not citations:
            for doc in documents:
                source = doc.get("source", "")
                title = doc.get("title", "")
                content = doc.get("content", "")
                if source and source.split("/")[-1] not in used_sources:
                    used_sources.add(source.split("/")[-1])
                    citations.append({
                        "title": title or source.split("/")[-1],
                        "source": source,
                        "relevance_score": round(doc.get("score", 0), 4),
                        "excerpt": self._extract_excerpt(content, 200),
                        "content_overlap": 0.0,
                    })

        return citations

    @staticmethod
    def _extract_excerpt(text: str, max_length: int = 200) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length].rsplit(" ", 1)[0] + "..."
