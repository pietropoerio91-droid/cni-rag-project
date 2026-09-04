import logging
from typing import Any

from langchain_core.language_models import BaseLLM

from src.inference.llm_client import LLMClient

logger = logging.getLogger(__name__)

GRADE_PROMPT = """Sei un valutatore di pertinenza. Dati una domanda e un documento, determina se il documento è pertinente per rispondere alla domanda.

Domanda: {question}
Documento: {document}

Rispondi solo con una parola: "pertinente" se il documento contiene informazioni utili per rispondere, altrimenti "non pertinente"."""


class GradeDocs:
    def __init__(self, llm: BaseLLM):
        self.client = LLMClient(llm)

    def grade(self, question: str, docs: list[dict[str, Any]]) -> str:
        if not docs:
            return "non pertinente"

        best_doc = max(docs, key=lambda d: d.get("score", 0))
        content = best_doc.get("content", "")[:2000]
        title = best_doc.get("title", "")
        source = best_doc.get("source", "")

        prompt = GRADE_PROMPT.format(
            question=question,
            document=f"Titolo: {title}\nFonte: {source}\nContenuto: {content}",
        )

        response = self.client.invoke([{"role": "user", "content": prompt}])
        result = response.strip().lower()

        if "pertinente" in result:
            return "pertinente"
        return "non pertinente"
