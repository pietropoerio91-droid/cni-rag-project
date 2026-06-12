import pytest

from src.governance.pii_filter import PIIFilter
from src.inference.citation_builder import CitationBuilder
from src.rag.prompt_builder import PromptBuilder


class TestRAGPipeline:
    def test_pii_filter_email(self):
        pf = PIIFilter(masked=True)
        text = "Contatta mario.rossi@example.com per info."
        result = pf.filter(text)
        assert "[EMAIL_REDACTED]" in result
        assert "mario.rossi@example.com" not in result

    def test_pii_filter_phone(self):
        pf = PIIFilter(masked=True)
        text = "Tel: 06 1234 5678"
        result = pf.filter(text)
        assert "[PHONE_REDACTED]" in result or "06 1234 5678" not in result

    def test_pii_filter_disabled(self):
        pf = PIIFilter(enabled=False)
        text = "mario.rossi@example.com"
        result = pf.filter(text)
        assert result == text

    def test_prompt_builder_format(self):
        results = [
            {"source": "https://www.cni.it/test1", "title": "Doc1", "content": "Contenuto del primo documento."},
            {"source": "https://www.cni.it/test2", "title": "Doc2", "content": "Contenuto del secondo documento."},
        ]
        messages = PromptBuilder.build_prompt("Qual è la normativa?", results)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Doc1" in messages[0]["content"]
        assert "Doc2" in messages[0]["content"]
        assert "Qual è la normativa?" in messages[0]["content"]

    def test_citation_builder(self):
        docs = [
            {"source": "https://www.cni.it/doc1", "title": "Documento 1", "content": "Contenuto lungo " * 100, "score": 0.95},
            {"source": "https://www.cni.it/doc2", "title": "Documento 2", "content": "Altro contenuto", "score": 0.85},
        ]
        cb = CitationBuilder()
        citations = cb.build(docs, "Test response")
        assert len(citations) == 2
        assert citations[0]["source"] == "https://www.cni.it/doc1"
        assert citations[0]["relevance_score"] == 0.95
        assert len(citations[0]["excerpt"]) <= 203
