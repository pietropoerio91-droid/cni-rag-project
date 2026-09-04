import logging

from langchain_core.language_models import BaseLLM

from src.inference.llm_client import LLMClient

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """Riscrivi la seguente domanda per migliorare la ricerca in un database vettoriale di documenti del Consiglio Nazionale degli Ingegneri (CNI).

La riscrittura deve:
- Usare termini chiave specifici del contesto ingegneristico/normativo
- Essere concisa (max 15 parole)
- Mantenere il significato originale

Domanda originale: {question}
Domanda riscritta:"""


class QueryRewriter:
    def __init__(self, llm: BaseLLM):
        self.client = LLMClient(llm)

    def rewrite(self, question: str) -> str:
        prompt = REWRITE_PROMPT.format(question=question)
        response = self.client.invoke([{"role": "user", "content": prompt}])
        rewritten = response.strip().strip('"').strip("'")
        logger.info(f"Query rewritten: '{question}' -> '{rewritten}'")
        return rewritten
