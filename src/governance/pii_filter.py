import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class PIIFilter:
    EMAIL_PATTERN = re.compile(r"\b[\w.%-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
    PHONE_PATTERN = re.compile(
        r"\b(?:\+?\d{1,3}[-.\s]?)?"
        r"(?:\(?\d{2,4}\)?[-./\s]?\d{3}[-.\s]?\d{3,4}"
        r"|\d{2,4}[-./\s]\d{4}[-.\s]?\d{4})\b"
    )
    FISCAL_CODE_PATTERN = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
    VAT_PATTERN = re.compile(r"\bIT\d{11}\b")
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    PATTERNS = {
        "email": EMAIL_PATTERN,
        "phone": PHONE_PATTERN,
        "fiscal_code": FISCAL_CODE_PATTERN,
        "vat": VAT_PATTERN,
        "ssn": SSN_PATTERN,
    }

    def __init__(self, enabled: bool = True, masked: bool = True):
        self.enabled = enabled
        self.masked = masked

    def filter(self, text: str, meta: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return text

        filtered = text
        found: list[str] = []

        for label, pattern in self.PATTERNS.items():
            matches = pattern.findall(filtered)
            if matches:
                found.extend(matches)
                if self.masked:
                    filtered = pattern.sub(f"[{label.upper()}_REDACTED]", filtered)

        if found:
            logger.info(f"Filtered {len(found)} potential PII items from text")

        return filtered
