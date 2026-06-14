import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Downloader:
    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_document(self, document: dict[str, Any]) -> Path:
        url = document.get("url", "unknown")
        safe_name = self._safe_filename(url)
        filepath = self.output_dir / f"{safe_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved document: {filepath}")
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
