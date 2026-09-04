import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class TextCleaner:
    BOILERPLATE_PATTERNS = [
        r"©\s*\d{4}\s+.*?(?:riservati|reserved|rights)",
        r"Tutti i diritti riservati",
        r"Cookie Policy",
        r"Privacy Policy",
        r"Informativa sulla privacy",
        r"Termini e condizioni",
        r"Condizioni d'uso",
        r"Accetta (?:tutti )?(?:i )?cookie",
        r"Questo sito utilizza cookie",
        r"Follow us on",
        r"Seguici su",
        r"Condividi su",
        r"Carica altri",
        r"Load more",
        r"^\s*$",
    ]

    CNI_FOOTER_BLOCK = re.compile(
        r"(?:\n|^)"
        r"(?:evidenza|pubblicazioni\s+CNI|servizi\s+convenzioni|l['\"]ingegnere\s+italiano|il\s+giornale\s+dell['\"]ingegnere)"
        r".*?"
        r"(?:CONSIGLIO\s+NAZIONALE\s+DEGLI\s+INGEGNERI)",
        re.DOTALL | re.IGNORECASE,
    )

    CNI_FOOTER_LINES = [
        r"^Per la corretta visualizzazione di questa pagina (?:è|e') necessario abilitare javascript\.?\s*$",
        r"^Cerca\s*$",
        r"^Home\s*$",
        r"^(?:Home\s+)?Eventi\s*$",
        r"^Visuale (?:giornaliera|settimanale|mensile)\s*$",
        r"^Giorno (?:precedente|successivo)\s*$",
        r"^Settimana (?:precedente|successiva)\s*$",
        r"^Mese (?:precedente|successivo)\s*$",
        r"^Nessun evento\s*$",
        r"^Benvenuto, da qui prosegui",
        r"^Accedi dal sistema interno",
        r"^pubblicazioni CNI$",
        r"^banca dati CNI$",
        r"^comitato italiano ingegneria dell'informazione$",
        r"^110%$",
        r"^network CNI$",
        r"^GdL formazione universitaria$",
        r"^ordini provinciali$",
        r"^ingenio al femminile$",
        r"^elezione ordini provinciali$",
        r"^gdl ponte sullo stretto$",
        r"^nuovo codice deontologico$",
        r"^Elenco siti tematici$",
        r"^REGOLAMENTO SUGLI ACCESSI$",
        r"^Dichiarazione di accessibilità$",
        r"^Whistleblowing$",
        r"^Note legali$",
        r"^URP$",
        r"^evidenza$",
        r"^servizi convenzioni$",
        r"^l'ingegnere italiano$",
        r"^il giornale dell'ingegnere$",
        r"^ingegneri e rappresentanza$",
        r"^avvisi$",
        r"^e bandi$",
        r"^amministrazione$",
        r"^trasparente$",
        r"^centro studi$",
        r"^scuola di formazione$",
        r"^working$",
        r"^CERTING$",
        r"^Elenco Biomedici e Clinici$",
        r"^Seleziona la tua lingua$",
        r"^MEDIA$",
        r"^News$",
        r"^Rassegna stampa$",
        r"^Comunicati stampa$",
        r"^Newsletter$",
        r"^Multimedia$",
        r"^Emergenza COVID-19$",
        r"^CONSIGLIO NAZIONALE DEGLI INGEGNERI.*$",
        r"^Privacy & Cookies$",
    ]

    def clean(self, text: str, meta: dict[str, Any] | None = None) -> str:
        text = self._remove_boilerplate(text)
        text = self._remove_cni_footer_block(text)
        text = self._remove_cni_footer_lines(text)
        text = self._normalize_whitespace(text)
        text = self._remove_repeated_lines(text)
        return text.strip()

    def _remove_boilerplate(self, text: str) -> str:
        for pattern in self.BOILERPLATE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text

    def _remove_cni_footer_block(self, text: str) -> str:
        return self.CNI_FOOTER_BLOCK.sub("", text)

    def _remove_cni_footer_lines(self, text: str) -> str:
        for pattern in self.CNI_FOOTER_LINES:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    @staticmethod
    def _remove_repeated_lines(text: str) -> str:
        lines = text.split("\n")
        seen: set[str] = set()
        unique_lines: list[str] = []
        for line in lines:
            stripped = line.strip().lower()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_lines.append(line)
            elif not stripped:
                unique_lines.append(line)
        return "\n".join(unique_lines)
