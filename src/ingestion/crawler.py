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
        self.max_depth = crawler_config.get("max_depth", 5)
        self.max_pages = crawler_config.get("max_pages", 1000)
        self.delay = crawler_config.get("delay", 0.3)
        self.timeout = crawler_config.get("timeout", 30)
        self.allowed_domains = crawler_config.get("allowed_domains", ["www.cni.it", "cni.it"])
        self.included_paths = crawler_config.get("included_paths", [])
        self.priority_paths = crawler_config.get("priority_paths", ["/media-ing/"])
        self.priority_max_depth = crawler_config.get("priority_max_depth", 8)
        self.focus_priority = crawler_config.get("focus_priority", True)
        self.max_links_per_page = crawler_config.get("max_links_per_page", 100)
        self.visited: set[str] = set()
        self.results: list[dict[str, Any]] = []
        self._queue: asyncio.Queue = None
        self._concurrency = 5

    async def crawl(self) -> list[dict[str, Any]]:
        logger.info(f"Starting crawl of {self.base_url} (max depth: {self.max_depth}, max pages: {self.max_pages})")
        self._queue = asyncio.Queue()
        await self._queue.put((self.base_url, 0, False))

        for priority_path in self.priority_paths:
            priority_url = urljoin(self.base_url, priority_path.lstrip("/"))
            if priority_url not in self.visited:
                await self._queue.put((priority_url, 0, True))

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
                url, depth, is_priority = await self._queue.get()
                try:
                    await self._process_url(client, url, depth, is_priority)
                finally:
                    self._queue.task_done()

    @staticmethod
    def _current_year() -> str:
        from datetime import date
        return str(date.today().year)

    def _is_priority_path(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/").lower()
        return any(pp in path for pp in self.priority_paths)

    def _is_current_year_url(self, url: str) -> bool:
        return self._current_year() in url

    async def _process_url(self, client: httpx.AsyncClient, url: str, depth: int, is_priority: bool = False) -> None:
        effective_max_depth = self.priority_max_depth if (is_priority or self._is_priority_path(url)) else self.max_depth
        if depth > effective_max_depth:
            return
        if len(self.visited) >= self.max_pages:
            return
        if url in self.visited:
            return
        if not self._is_allowed(url):
            return

        self.visited.add(url)
        logger.info(f"Visiting [{len(self.visited)}/{self.max_pages}] {url} (depth {depth}, max {effective_max_depth})")

        try:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                html = response.text
                page_data = self._process_html(url, html)
                if page_data:
                    self.results.append(page_data)

                links = self._extract_links(url, html, is_priority)
                for link in links:
                    await asyncio.sleep(self.delay)
                    link_is_priority = is_priority or self._is_priority_path(link)
                    await self._queue.put((link, depth + 1, link_is_priority))

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

    def _extract_links(self, base_url: str, html: str, on_priority_page: bool = False) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            if len(links) >= self.max_links_per_page:
                break
            href = anchor["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https") or parsed.fragment:
                continue
            clean_url = self._normalize_url(full_url)
            if not self._is_allowed(clean_url) or clean_url in self.visited:
                continue
            if self.focus_priority and on_priority_page and not self._is_priority_path(clean_url):
                continue
            links.append(clean_url)
        links.sort(key=lambda u: (
            not self._is_priority_path(u),
            not self._is_current_year_url(u),
        ))
        return links

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        query = parsed.query
        if not query:
            return f"{parsed.scheme}://{parsed.netloc}{path}"
        return f"{parsed.scheme}://{parsed.netloc}{path}?{query}"

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

        return {
            "url": url,
            "title": title,
            "content": text,
            "raw_html": html,
            "meta": meta,
        }

    def _process_pdf(self, url: str, content: bytes) -> dict[str, Any] | None:
        import base64
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
                "raw_pdf": base64.b64encode(content).decode("ascii"),
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
