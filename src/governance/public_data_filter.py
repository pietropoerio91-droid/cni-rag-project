import logging
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "normativa": "Normative and regulations",
    "chi_siamo": "About CNI - organization information",
    "organi": "Governing bodies",
    "commissioni": "Commissions and committees",
    "documenti": "Official documents",
    "news": "News and communications",
    "servizi": "Services for engineers",
    "contatti": "Contact information",
    "albo": "Professional register",
    "formazione": "Training and education",
}

DENIED_KEYWORDS = [
    "credenziali",
    "non-pubblico",
]


class PublicDataFilter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_public(self, url: str, content: str, meta: dict[str, Any] | None = None) -> bool:
        if not self.enabled:
            return True

        url_lower = url.lower()

        denied_patterns = ["/wp-admin", "/wp-json", "/wp-login", "/private", "/restricted"]
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
        for key in ALLOWED_CATEGORIES:
            if key.replace("_", "-") in url_lower or key in url_lower:
                return key
        return "generico"
