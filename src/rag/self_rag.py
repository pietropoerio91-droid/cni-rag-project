import logging
from typing import Any

from langchain_core.language_models import BaseLLM

from src.inference.llm_client import LLMClient

logger = logging.getLogger(__name__)

SELF_CHECK_PROMPT = """Sei un verificatore di accuratezza. Dati una domanda, una risposta e i documenti di riferimento, determina se la risposta è completamente supportata dai documenti.

Domanda: {question}
Risposta: {response}
Documenti:
{documents}

La risposta contiene informazioni NON presenti nei documenti? Rispondi solo con una parola: "accurata" se la risposta è supportata dai documenti, altrimenti "inaccurata"."""


class SelfRAG:
    def __init__(self, llm: BaseLLM):
        self.client = LLMClient(llm)

    def check(self, question: str, response: str, docs: list[dict[str, Any]]) -> str:
        if not response:
            return "accurata"

        doc_texts = []
        for d in docs[:3]:
            title = d.get("title", "Senza titolo")
            content = d.get("content", "")[:1000]
            doc_texts.append(f"[{title}]\n{content}\n")

        prompt = SELF_CHECK_PROMPT.format(
            question=question,
            response=response,
            documents="\n---\n".join(doc_texts),
        )

        result = self.client.invoke([{"role": "user", "content": prompt}])
        result = result.strip().lower()

        if "inaccurata" in result:
            return "inaccurata"
        return "accurata"
