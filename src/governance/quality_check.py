import logging
from typing import Any

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class QualityChecker:
    def __init__(self):
        config = ConfigLoader.get_rag_config()
        qc = config.get("quality", {})
        self.min_len = qc.get("min_content_length", 200)
        self.max_len = qc.get("max_content_length", 100000)
        self.max_repetition_ratio = qc.get("max_repetition_ratio", 0.3)
        self.required_languages = qc.get("required_languages", ["it"])
        self.min_content_ratio = qc.get("min_content_ratio", 0.3)

    NAV_KEYWORDS = {
        "cerca", "home", "login", "logout", "registrati", "accedi",
        "menu", "navigazione", "navigation", "footer", "cookie",
        "pubblicazioni cni", "banca dati cni", "network cni",
        "ordini provinciali", "amministrazione trasparente",
        "privacy", "note legali", "urp", "whistleblowing",
        "news", "rassegna stampa", "comunicati stampa", "newsletter",
        "multimedia", "evidenza", "servizi convenzioni",
        "centro studi", "scuola di formazione",
    }

    def check(self, text: str, meta: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
        issues: list[str] = []

        if not text or not text.strip():
            issues.append("Empty content")
            return False, issues

        if len(text) < self.min_len:
            issues.append(f"Content too short: {len(text)} chars (min {self.min_len})")
            return False, issues

        if len(text) > self.max_len:
            issues.append(f"Content too long: {len(text)} chars (max {self.max_len})")
            return False, issues

        repetition_ratio = self._compute_repetition_ratio(text)
        if repetition_ratio > self.max_repetition_ratio:
            issues.append(f"High repetition ratio: {repetition_ratio:.2f} (max {self.max_repetition_ratio})")
            return False, issues

        content_ratio = self._compute_content_ratio(text)
        if content_ratio < self.min_content_ratio:
            issues.append(f"Low content ratio: {content_ratio:.2f} (min {self.min_content_ratio})")
            return False, issues

        return True, issues

    def _compute_content_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        lines = text.strip().split("\n")
        meaningful = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if any(nav in lower for nav in self.NAV_KEYWORDS):
                continue
            if len(stripped.split()) >= 3:
                meaningful += 1
        total_non_empty = sum(1 for l in lines if l.strip())
        return meaningful / max(total_non_empty, 1)

    ITALIAN_STOP_WORDS = {
        "il", "lo", "la", "gli", "le", "i", "l'", "un", "uno", "una",
        "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        "e", "ed", "o", "ma", "che", "chi", "cui", "se", "come", "dove",
        "del", "della", "degli", "delle", "dei", "dell'",
        "al", "allo", "alla", "agli", "alle", "all'",
        "dal", "dallo", "dalla", "dagli", "dalle", "dall'",
        "nel", "nello", "nella", "negli", "nelle", "nell'",
        "sul", "sullo", "sulla", "sugli", "sulle", "sull'",
        "è", "non", "si", "ci", "vi", "mi", "ti", "lo", "la",
        "ho", "hai", "ha", "hanno", "sono", "sei", "siamo", "siete",
        "questo", "questa", "questi", "queste", "quello", "quella",
        "più", "molto", "troppo", "tanto", "poco", "anche",
        "già", "sempre", "mai", "ora", "dopo", "prima", "poi",
        "essere", "avere", "fare", "dire", "volere", "potere",
        "ciò", "cosa", "quel", "tale", "stato", "stata", "loro",
        "suo", "sua", "suoi", "sue", "mio", "mia", "tuo", "tua",
        "c'", "d'", "n'", "s'", "m'", "t'", "v'",
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    }

    @staticmethod
    def _compute_repetition_ratio(text: str) -> float:
        if not text:
            return 0.0
        words = [w.strip(".,;:!?()[]{}«»\"'-") for w in text.lower().split()]
        words = [w for w in words if len(w) > 2 and w not in QualityChecker.ITALIAN_STOP_WORDS]
        if not words:
            return 0.0
        unique_words = set(words)
        return 1.0 - (len(unique_words) / len(words))
