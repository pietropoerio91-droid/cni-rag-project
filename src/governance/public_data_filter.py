import logging
from typing import Any

logger = logging.getLogger(__name__)

DENIED_KEYWORDS = [
    "credenziali",
    "non-pubblico",
]

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "news": [
        "/media-ing/news", "/news", "/comunicati-stampa", "/rassegna-stampa",
        "/media-ing/multimedia", "/media-ing/area-covid",
    ],
    "documenti": [
        "/documenti", "/atti", "/images/atti", "/images/bilanci",
        "/images/delibere", "/images/verbali", "/images/pubblicazioni",
        "/images/modulistica",
    ],
    "normativa": [
        "/normativa", "/decreti", "/leggi", "/regolamenti",
        "/images/normativa", "/images/atti_generali",
    ],
    "formazione": [
        "/formazione", "/corsi", "/crediti", "/cfp",
        "/scuola-formazione", "/images/formazione",
    ],
    "commissioni": [
        "/commissioni", "/comitati", "/gruppi-lavoro",
        "/images/commissioni",
    ],
    "organi": [
        "/organi", "/consiglio", "/presidenza", "/cni/organi",
    ],
    "servizi": [
        "/servizi", "/sportello", "/convenzioni", "/images/servizi",
    ],
    "eventi": [
        "/eventi", "/convegni", "/seminari",
    ],
    "temi": [
        "/temi", "/sicurezza", "/ambiente", "/energia",
    ],
    "giornale": [
        "/il-giornale-dell-ingegnere", "/giornale-ingegnere",
    ],
    "albo": [
        "/albo", "/elenchi", "/iscrizione", "/registro",
    ],
    "contatti": [
        "/contatti", "/contatta", "/sede",
    ],
    "chi_siamo": [
        "/chi-siamo", "/cni/chi-siamo",
    ],
}


class PublicDataFilter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_public(self, url: str, content: str, meta: dict[str, Any] | None = None) -> bool:
        if not self.enabled:
            return True

        url_lower = url.lower()

        denied_patterns = ["/administrator", "/component/", "/wp-admin", "/wp-json", "/wp-login", "/private", "/restricted"]
        if any(p in url_lower for p in denied_patterns):
            logger.info(f"Skipping restricted URL: {url}")
            return False

        content_lower = content.lower()
        for keyword in DENIED_KEYWORDS:
            if keyword in content_lower:
                logger.info(f"Content contains denied keyword '{keyword}' in {url}")
                return False

        return True

    def categorize(self, url: str, content: str) -> str:
        url_lower = url.lower()
        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if pattern in url_lower:
                    return category
        return "generico"
