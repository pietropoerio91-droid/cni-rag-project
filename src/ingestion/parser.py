import logging
import re
from typing import Any

import trafilatura
from trafilatura import extract as trafilatura_extract

logger = logging.getLogger(__name__)


class DocumentParser:
    def parse_html(self, html: str, url: str | None = None) -> str:
        result = trafilatura_extract(html, output_format="txt", include_comments=False, include_tables=True)
        if result:
            return result
        logger.warning(f"Trafilatura extraction failed for {url}, falling back to regex")
        return self._regex_fallback(html)

    def parse_pdf_text(self, text: str) -> str:
        lines = text.split("\n")
        cleaned = [line.strip() for line in lines if line.strip()]
        return "\n".join(cleaned)

    @staticmethod
    def _regex_fallback(html: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n", text)
        return text.strip()
