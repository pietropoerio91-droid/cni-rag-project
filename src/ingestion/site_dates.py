"""Date di pubblicazione degli articoli lette dalla ricerca interna del sito.

Il template Joomla di cni.it non mostra la data nelle pagine degli articoli (niente
`<time>`, meta o JSON-LD), ma la ricerca del sito (`/ricerca`, Joomla Smart Search)
la riporta per ogni risultato:

    <time class="result__date" datetime="2026-11-19T14:25:30+01:00">19 Novembre 2026</time>

E' la data di pubblicazione salvata nel CMS. Si scarica una volta, in fase di
ingestione, una mappa URL -> data interrogando la ricerca con poche parole molto
frequenti e scorrendo tutte le pagine dei risultati (100 per pagina); a ogni
domanda non serve nessuna chiamata al sito.

Note sui contenuti:
  - /evidenza/ (eventi): la data e' quella dell'evento, anche futura. Si tiene.
  - contenitori annuali ("Rassegna stampa 2022"): data convenzionale al 1 gennaio.
  - pagine istituzionali (/cni/consiglio, /temi/...): la data e' quella di
    creazione, ma il contenuto viene aggiornato. Si usa la data solo per le
    sezioni in `dates.dated_sections`; le altre restano senza data (neutre).
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_TERMS = ("ingegneri", "cni", "consiglio", "ingegneria", "nazionale", "presidente", "ordine", "professione")
DEFAULT_PATH = "data/dates/site_dates.json"
DEFAULT_SECTIONS = ("/media-ing", "/evidenza", "/notizie-internazionali", "/il-giornale-dell-ingegnere",
                    "/area-cni/200-elezioni-ordini-provinciali")
PAGE_SIZE = 100
MAX_RESULTS = 20000  # limite di sicurezza per termine

_ITEM = re.compile(r'class="result__item">(.*?)</li>', re.S)
_URL = re.compile(r'class="result__title-url">([^<]+)<')
_DATE = re.compile(r'class="result__date"[^>]*\bdatetime="([^"]+)"|\bdatetime="([^"]+)"[^>]*class="result__date"')
_TOTAL = re.compile(r"(\d[\d.]*)\s*risultat", re.I)


def url_key(url: str) -> str:
    """Chiave di confronto fra URL del crawler e URL della ricerca: senza schema, www, slash finale."""
    p = urlparse(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/")
    return f"{host}{path}?{p.query}" if p.query else f"{host}{path}"


def parse_results(page: str) -> list[tuple[str, str]]:
    """(url, data AAAA-MM-GG) per ogni risultato di una pagina di /ricerca."""
    out = []
    for item in _ITEM.findall(page):
        u, d = _URL.search(item), _DATE.search(item)
        if not (u and d):
            continue
        value = d.group(1) or d.group(2)
        try:
            day = datetime.fromisoformat(value).date()
        except ValueError:
            continue
        out.append((html.unescape(u.group(1)).strip(), day.isoformat()))
    return out


def total_results(page: str) -> int | None:
    m = _TOTAL.search(re.sub(r"<[^>]+>", " ", page))
    return int(m.group(1).replace(".", "")) if m else None


def fetch_site_dates(base_url: str = "https://www.cni.it", terms: tuple[str, ...] = DEFAULT_TERMS,
                     delay: float = 1.0, timeout: float = 60.0, client=None,
                     user_agent: str = "CNI-RAG-Bot") -> dict[str, dict[str, str]]:
    """Interroga /ricerca per ogni termine, pagina per pagina, e restituisce url_key -> data."""
    import httpx

    own = client is None
    client = client or httpx.Client(timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=True)
    dates: dict[str, dict[str, str]] = {}
    try:
        for term in terms:
            start, total = 0, None
            while True:
                r = client.get(f"{base_url.rstrip('/')}/ricerca",
                               params={"q": term, "limit": PAGE_SIZE, "start": start, "o": "date", "od": "desc"})
                r.raise_for_status()
                results = parse_results(r.text)
                total = total if total is not None else total_results(r.text)
                for url, day in results:
                    dates.setdefault(url_key(url), {"url": url, "date": day})
                logger.info(f"ricerca '{term}' da {start}: {len(results)} risultati (totale {total}), mappa {len(dates)}")
                start += PAGE_SIZE
                # Alcune pagine hanno meno di 100 risultati validi anche a meta' elenco:
                # ci si ferma sul totale dichiarato dalla ricerca o su una pagina vuota.
                if not _ITEM.search(r.text) or (total is not None and start >= total) or start >= MAX_RESULTS:
                    break
                time.sleep(delay)
            time.sleep(delay)
    finally:
        if own:
            client.close()
    return dates


def save_site_dates(dates: dict[str, dict[str, str]], path: str | Path = DEFAULT_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": date.today().isoformat(), "count": len(dates), "dates": dates}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def only_dated_sections(dates: dict[str, dict[str, str]],
                        sections: tuple[str, ...] | None = None) -> dict[str, dict[str, str]]:
    return {k: v for k, v in dates.items() if in_dated_section(v.get("url", ""), sections)}


def load_site_dates(path: str | Path = DEFAULT_PATH,
                    sections: tuple[str, ...] | None = None) -> dict[str, dict[str, str]]:
    """Mappa salvata da `save_site_dates`, ristretta alle sezioni datate; {} se il file non c'e'.

    Il file contiene tutte le pagine trovate dalla ricerca: il filtro per sezione si
    applica qui, cosi' cambiare `dates.dated_sections` non richiede un nuovo download.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        dates = json.loads(path.read_text(encoding="utf-8")).get("dates", {})
    except (OSError, ValueError) as exc:
        logger.warning(f"Mappa delle date illeggibile {path}: {exc}")
        return {}
    return only_dated_sections(dates, sections)


def in_dated_section(url: str, sections: tuple[str, ...] | None = None) -> bool:
    path = urlparse(url).path.lower()
    return any(path.startswith(s.rstrip("/").lower() + "/") or path == s.rstrip("/").lower()
               for s in (sections or DEFAULT_SECTIONS))


def lookup(site_dates: dict[str, dict[str, str]] | None, url: str) -> dict[str, str]:
    """Data di `url` nella mappa (gia' ristretta alle sezioni datate da load_site_dates)."""
    if not site_dates or not url:
        return {}
    hit = site_dates.get(url_key(url))
    if not hit:
        return {}
    return {"date": hit["date"], "date_source": "sito:ricerca", "date_precision": "day"}


def site_dates_settings() -> dict:
    from src.core.config_loader import ConfigLoader

    cfg = ConfigLoader.get_rag_config()
    dates = cfg.get("dates", {}) or {}
    return {
        "path": dates.get("site_dates_file", DEFAULT_PATH),
        "refresh_on_ingest": dates.get("refresh_on_ingest", True),
        "delay": float(dates.get("search_delay", 0.5)),
        "terms": tuple(dates.get("search_terms") or DEFAULT_TERMS),
        "base_url": (cfg.get("crawler", {}) or {}).get("base_url", "https://www.cni.it"),
        "sections": tuple(dates.get("dated_sections") or DEFAULT_SECTIONS),
    }


def refresh_site_dates() -> dict[str, dict[str, str]]:
    """Scarica di nuovo la mappa e la salva; se il sito non risponde tiene quella su file."""
    s = site_dates_settings()
    try:
        dates = fetch_site_dates(s["base_url"], s["terms"], s["delay"])
    except Exception as exc:  # rete, HTTP: si prosegue con la mappa precedente
        logger.warning(f"Mappa delle date non aggiornata ({exc}): uso {s['path']}")
        return load_site_dates(s["path"], s["sections"])
    if dates:
        save_site_dates(dates, s["path"])
        return only_dated_sections(dates, s["sections"])
    return load_site_dates(s["path"], s["sections"])
