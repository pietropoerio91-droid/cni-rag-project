import base64
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Downloader:
    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._html_dir = self.output_dir / "html"
        self._pdf_dir = self.output_dir / "pdf"
        self._html_dir.mkdir(parents=True, exist_ok=True)
        self._pdf_dir.mkdir(parents=True, exist_ok=True)

    def save_document(self, document: dict[str, Any]) -> Path:
        url = document.get("url", "unknown")
        safe_name = self._safe_filename(url)

        raw_html = document.pop("raw_html", None)
        raw_pdf_b64 = document.pop("raw_pdf", None)

        if raw_html is not None:
            html_path = self._html_dir / f"{safe_name}.html"
            html_path.write_text(raw_html, encoding="utf-8")
            logger.debug(f"Saved raw HTML: {html_path}")
            document.setdefault("meta", {})["raw_html_path"] = str(html_path.relative_to(self.output_dir))

        if raw_pdf_b64 is not None:
            pdf_path = self._pdf_dir / f"{safe_name}.pdf"
            pdf_path.write_bytes(base64.b64decode(raw_pdf_b64))
            logger.debug(f"Saved raw PDF: {pdf_path}")
            document.setdefault("meta", {})["raw_pdf_path"] = str(pdf_path.relative_to(self.output_dir))

        filepath = self.output_dir / f"{safe_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved JSON metadata: {filepath}")
        return filepath

    def save_documents(self, documents: list[dict[str, Any]]) -> list[Path]:
        return [self.save_document(doc) for doc in documents]

    def load_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for filepath in sorted(self.output_dir.glob("*.json")):
            with open(filepath, "r", encoding="utf-8") as f:
                documents.append(json.load(f))
        logger.info(f"Loaded {len(documents)} documents from {self.output_dir}")
        return documents

    @staticmethod
    def _safe_filename(url: str) -> str:
        safe = url.replace("https://", "").replace("http://", "")
        safe = safe.replace("/", "_").replace("?", "_").replace("&", "_")
        safe = safe.replace("=", "_").replace("%", "_")
        return safe[:200]
