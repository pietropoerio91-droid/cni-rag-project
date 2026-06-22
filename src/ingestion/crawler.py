import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class CNICrawler:
    def __init__(self):
        config = ConfigLoader.get_rag_config()
        crawler_config = config.get("crawler", {})
        self.base_url = crawler_config.get("base_url", "https://www.cni.it")
        self.max_depth = crawler_config.get("max_depth", 3)
        self.max_pages = crawler_config.get("max_pages", 100)
        self.delay = crawler_config.get("delay", 1.0)
        self.timeout = crawler_config.get("timeout", 30)
        self.allowed_domains = crawler_config.get("allowed_domains", ["www.cni.it", "cni.it"])
        self.included_paths = crawler_config.get("included_paths", [])
        self.visited: set[str] = set()
        self.results: list[dict[str, Any]] = []
        self._queue: asyncio.Queue = None
        self._concurrency = 5

    async def crawl(self) -> list[dict[str, Any]]:
        logger.info(f"Starting crawl of {self.base_url} (max depth: {self.max_depth}, max pages: {self.max_pages})")
        self._queue = asyncio.Queue()
        await self._queue.put((self.base_url, 0))

        workers = [asyncio.create_task(self._worker()) for _ in range(self._concurrency)]
        await self._queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        logger.info(f"Crawl complete. Visited {len(self.visited)} pages, collected {len(self.results)} documents.")
        return self.results

    async def _worker(self) -> None:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            while True:
                url, depth = await self._queue.get()
                try:
                    await self._process_url(client, url, depth)
                finally:
                    self._queue.task_done()

    async def _process_url(self, client: httpx.AsyncClient, url: str, depth: int) -> None:
        if depth > self.max_depth:
            return
        if len(self.visited) >= self.max_pages:
            return
        if url in self.visited:
            return
        if not self._is_allowed(url):
            return

        self.visited.add(url)
        logger.info(f"Visiting [{len(self.visited)}/{self.max_pages}] {url} (depth {depth})")

        try:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                html = response.text
                page_data = self._process_html(url, html)
                if page_data:
                    self.results.append(page_data)

                links = self._extract_links(url, html)
                for link in links:
                    await asyncio.sleep(self.delay)
                    await self._queue.put((link, depth + 1))

            elif "application/pdf" in content_type:
                pdf_data = self._process_pdf(url, response.content)
                if pdf_data:
                    self.results.append(pdf_data)

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error for {url}: {e.response.status_code}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for {url}")
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")

    EXCLUDED_EXTENSIONS = {
        ".xml", ".json", ".rss", ".atom", ".xsl",
        ".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".mp4", ".mp3", ".doc", ".docx", ".xls", ".xlsx", ".zip",
        ".woff", ".woff2", ".ttf", ".eot",
    }

    DENIED_PATTERNS = ["/wp-admin", "/wp-json", "/wp-login", "/xmlrpc", "/feed/"]

    def _is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain not in self.allowed_domains and not any(domain.endswith(f".{d}") for d in self.allowed_domains):
            return False

        path = parsed.path.rstrip("/").lower()

        for pat in self.DENIED_PATTERNS:
            if pat in path:
                return False

        ext = path[path.rfind("."):] if "." in path.split("/")[-1] else ""
        if ext in self.EXCLUDED_EXTENSIONS:
            return False

        if self.included_paths and path:
            if not any(path.startswith(p) for p in self.included_paths):
                return False
        return True

    def _extract_links(self, base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            if len(links) >= 50:
                break
            href = anchor["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme in ("http", "https") and not parsed.fragment:
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
                if self._is_allowed(clean_url) and clean_url not in self.visited:
                    links.append(clean_url)
        return links

    def _process_html(self, url: str, html: str) -> dict[str, Any] | None:
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        text = main_content.get_text(separator="\n", strip=True) if main_content else ""

        if len(text) < 50:
            return None

        meta: dict[str, Any] = {
            "source": url,
            "title": title,
            "type": "html",
        }
        meta_tags = soup.find_all("meta")
        for tag in meta_tags:
            name = tag.get("name") or tag.get("property", "")
            content = tag.get("content", "")
            if name and content:
                meta[name] = content

        return {"url": url, "title": title, "content": text, "meta": meta}

    def _process_pdf(self, url: str, content: bytes) -> dict[str, Any] | None:
        import fitz
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            if len(text) < 50:
                return None
            return {
                "url": url,
                "title": url.split("/")[-1],
                "content": text,
                "meta": {"source": url, "type": "pdf"},
            }
        except Exception as e:
            logger.error(f"Error parsing PDF {url}: {e}")
            return None

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": "CNI-RAG-Bot/1.0 (research project; contact@example.com)",
            "Accept": "text/html,application/pdf,*/*",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        }
