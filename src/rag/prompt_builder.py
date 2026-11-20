from typing import Any


class PromptBuilder:
    SYSTEM_TEMPLATE = """Sei un assistente specializzato nella consultazione dei dati pubblici del Consiglio Nazionale degli Ingegneri (CNI).

REGOLA FONDAMENTALE: Devi basarti ESCLUSIVAMENTE sui documenti forniti qui sotto. Se i documenti non contengono informazioni sufficienti per rispondere, devi dirlo chiaramente con una frase come "I documenti disponibili non contengono informazioni sufficienti su questo argomento."

NON usare la tua conoscenza pregressa per arricchire la risposta.
NON inventare informazioni, date, nomi o dettagli che non compaiono nei documenti.
Se un documento citato non contiene realmente l'informazione che stai fornendo, NON citarlo.

Quando citi un documento, usa SEMPRE il titolo completo (es. "Titolari di incarichi politici"). NON usare mai "Documento 1", "Documento 2" ecc. NON inventare punteggi o score: quelli vengono calcolati separatamente dal sistema.

Documenti di riferimento (USA SOLO QUESTI):
{context}

Domanda: {question}

Rispondi basandoti esclusivamente sui documenti sopra riportati."""

    DATE_RULE = """DATE DEI DOCUMENTI: accanto al titolo di alcuni documenti e' indicata la data. Se due documenti riportano informazioni diverse sullo stesso argomento (ad esempio cariche, nomine, scadenze o norme aggiornate), considera valida quella del documento piu' recente e indica la data della fonte che usi."""

    _MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
             "agosto", "settembre", "ottobre", "novembre", "dicembre")

    @staticmethod
    def format_date(value: str, precision: str = "day") -> str:
        """Formatta la data per il prompt: "2022-11-15" -> "15/11/2022"; con precisione mensile o annuale "novembre 2022" / "2022"."""
        if not value or len(value) < 10:
            return ""
        y, m, d = value[:4], value[5:7], value[8:10]
        if precision == "year":
            return y
        if precision == "month":
            try:
                return f"{PromptBuilder._MESI[int(m) - 1]} {y}"
            except (ValueError, IndexError):
                return y
        return f"{d}/{m}/{y}"

    @staticmethod
    def _context(results: list[dict[str, Any]]) -> str:
        context_parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "Sconosciuta")
            title = r.get("title", "Senza titolo")
            content = r.get("content", "")
            data = PromptBuilder.format_date(r.get("date", ""), r.get("date_precision") or "day")
            header = f"[Posizione {i} - {title} - data: {data}]" if data else f"[Posizione {i} - {title}]"
            context_parts.append(f"{header}\nFonte: {source}\n{content}\n")
        return "\n---\n".join(context_parts)

    @staticmethod
    def _system_text(context: str, question: str, results: list[dict[str, Any]]) -> str:
        text = PromptBuilder.SYSTEM_TEMPLATE.format(context=context, question=question)
        # La regola sulle date compare solo se almeno un documento e' datato: con un
        # indice senza date il prompt resta identico a quello valutato nella tesi.
        if any(r.get("date") for r in results):
            marker = "Documenti di riferimento (USA SOLO QUESTI):"
            text = text.replace(marker, f"{PromptBuilder.DATE_RULE}\n\n{marker}", 1)
        return text

    @staticmethod
    def build_prompt(question: str, results: list[dict[str, Any]]) -> list[dict[str, str]]:
        context = PromptBuilder._context(results)

        system_msg = {
            "role": "system",
            "content": PromptBuilder._system_text(context, question, results),
        }

        user_msg = {
            "role": "user",
            "content": question,
        }

        return [system_msg, user_msg]

    @staticmethod
    def build_stream_prompt(question: str, results: list[dict[str, Any]]) -> str:
        context = PromptBuilder._context(results)

        return PromptBuilder._system_text(context, question, results)
