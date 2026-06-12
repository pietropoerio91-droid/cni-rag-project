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

    def clean(self, text: str, meta: dict[str, Any] | None = None) -> str:
        text = self._remove_boilerplate(text)
        text = self._normalize_whitespace(text)
        text = self._remove_repeated_lines(text)
        return text.strip()

    def _remove_boilerplate(self, text: str) -> str:
        for pattern in self.BOILERPLATE_PATTERNS:
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
