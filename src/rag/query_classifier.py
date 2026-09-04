import logging
from typing import Any

logger = logging.getLogger(__name__)


class QueryClassifier:
    CATEGORIES = {
        "normativa": ["normativ", "norma", "norme", "legge", "decreto", "regolament", "codice", "articolo"],
        "organi": ["organo", "consiglio", "presidente", "vicepresidente", "segretario", "tesoriere"],
        "commissioni": ["commissione", "comitato", "gruppo", "tavolo"],
        "albo": ["albo", "elenco", "iscrizione", "registro", "ingegnere", "professione"],
        "formazione": ["formazione", "credito", "cfp", "corso", "aggiornamento", "seminario"],
        "servizi": ["servizio", "sportello", "assistenza", "modello", "domanda"],
        "documenti": ["documento", "bilancio", "relazione", "verbale", "delibera"],
        "contatti": ["contatto", "sede", "telefono", "email", "pec", "indirizzo"],
    }

    def classify(self, query: str) -> str:
        query_lower = query.lower()
        scores: dict[str, int] = {}

        for category, keywords in self.CATEGORIES.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scores[category] = score

        if not scores:
            return "generico"

        best_category = max(scores, key=scores.get)
        logger.debug(f"Classified query as '{best_category}'")
        return best_category

    def get_filter(self, query: str) -> dict[str, Any] | None:
        category = self.classify(query)
        if category != "generico":
            return {"category": category}
        return None
