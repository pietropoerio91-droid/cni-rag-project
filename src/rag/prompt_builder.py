from typing import Any


class PromptBuilder:
    SYSTEM_TEMPLATE = """Sei un assistente specializzato nella consultazione dei dati pubblici del Consiglio Nazionale degli Ingegneri (CNI).

Utilizza SOLO i documenti forniti nel contesto per rispondere alla domanda dell'utente.
Se i documenti non contengono informazioni sufficienti per rispondere, dillo chiaramente.

Linee guida:
- Rispondi sempre in ITALIANO
- Cita le fonti usando il formato [Fonte: titolo documento]
- Sii preciso e conciso
- Se una informazione non è presente nei documenti, NON inventarla
- Quando rilevante, menziona la sezione del sito CNI da cui proviene l'informazione

Documenti di riferimento:
{context}

Domanda: {question}

Rispondi in modo completo e accurato basandoti esclusivamente sui documenti forniti sopra."""

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
