from typing import Any


class PromptBuilder:
    SYSTEM_TEMPLATE = """Sei un assistente specializzato nella consultazione dei dati pubblici del Consiglio Nazionale degli Ingegneri (CNI).

REGOLA FONDAMENTALE: Devi basarti ESCLUSIVAMENTE sui documenti forniti qui sotto. Se i documenti non contengono informazioni sufficienti per rispondere, devi dirlo chiaramente con una frase come "I documenti disponibili non contengono informazioni sufficienti su questo argomento."

NON usare la tua conoscenza pregressa per arricchire la risposta.
NON inventare informazioni, date, nomi o dettagli che non compaiono nei documenti.
Se un documento citato non contiene realmente l'informazione che stai fornendo, NON citarlo.

Formatta le citazioni cosi: [Fonte: titolo documento]

Documenti di riferimento (USA SOLO QUESTI):
{context}

Domanda: {question}

Rispondi basandoti esclusivamente sui documenti sopra riportati."""

    @staticmethod
    def build_prompt(question: str, results: list[dict[str, Any]]) -> list[dict[str, str]]:
        context_parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "Sconosciuta")
            title = r.get("title", "Senza titolo")
            content = r.get("content", "")
            context_parts.append(f"[Documento {i} - {title}]\nFonte: {source}\n{content}\n")

        context = "\n---\n".join(context_parts)

        system_msg = {
            "role": "system",
            "content": PromptBuilder.SYSTEM_TEMPLATE.format(context=context, question=question),
        }

        user_msg = {
            "role": "user",
            "content": question,
        }

        return [system_msg, user_msg]

    @staticmethod
    def build_stream_prompt(question: str, results: list[dict[str, Any]]) -> str:
        context_parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "Sconosciuta")
            title = r.get("title", "Senza titolo")
            content = r.get("content", "")
            context_parts.append(f"[Documento {i} - {title}]\nFonte: {source}\n{content}\n")

        context = "\n---\n".join(context_parts)

        return PromptBuilder.SYSTEM_TEMPLATE.format(context=context, question=question)
