"""Data di riferimento di un documento, per dare peso ai documenti piu' recenti.

Perche' serve
-------------
Il portale CNI contiene notizie di anni diversi sullo stesso argomento: un
comunicato del 2016 ("Zambrano al timone del CNI") e uno del 2022 ("Eletti i
nuovi vertici") parlano entrambi del presidente. Senza una data il recupero li
tratta allo stesso modo e il generatore puo' mescolarli (domanda Q01).

Da dove si ricava
-----------------
Il template Joomla del portale non pubblica la data nei metadati HTML (nessun
`<meta>` di pubblicazione, nessun `<time>`), quindi si usano piu' fonti, in
ordine di affidabilita', e ci si ferma alla prima che risponde:

1. metadati della pagina (`article:published_time`, `datePublished`, JSON-LD,
   `<time datetime>`): assenti sul portale CNI di oggi, ma presenti su molti
   siti e quindi pronti per nuove fonti;
2. intestazione delle circolari ("Circolare n. 123 ... del 15/03/2024");
3. data per esteso nello slug dell'URL ("/345-13-11-2013-armando-zambrano-...");
4. firma dei comunicati stampa ("Roma, 16 novembre 2026"), accettata solo se
   l'anno coincide con quello dell'URL quando l'URL ne riporta uno;
5. anno della categoria nell'URL delle notizie ("/media-ing/news/230-2022/...")
   o di un segmento ("/area-covid-2020/", "/2022/");
6. nome del file dei PDF ("Newsletter_3_-_gennaio_2023.pdf");
7. metadati interni del PDF (data di creazione).

Volutamente NON si cerca "una data qualsiasi" nel testo: le pagine istituzionali
contengono date di nascita e di mandato (es. /cni/consiglio) che darebbero una
data sbagliata. Un documento senza data resta senza data e riceve un peso
neutro (vedi src/rag/recency.py).

Formato restituito
------------------
`{"date": "AAAA-MM-GG", "date_source": <fonte>, "date_precision": "day"|"month"|"year"}`
oppure `{}`. Con precisione mensile o annuale il giorno (e il mese) sono
convenzionali: 15 del mese, 1 luglio dell'anno, cioe' il centro dell'intervallo.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_MESI_RE = "|".join(MESI)

ANNO_MINIMO = 1990

# Chiavi dei tag <meta> salvate dal crawler (name/property -> content), in ordine
# di preferenza: la data di modifica descrive meglio l'attualita' del contenuto.
META_KEYS = (
    "article:modified_time", "og:updated_time", "datemodified", "dcterms.modified", "last-modified",
    "article:published_time", "og:published_time", "datepublished", "dc.date", "dc.date.issued",
    "dcterms.date", "dcterms.created", "pubdate", "publish_date", "publication_date", "date",
)

_ISO = re.compile(r"(?P<y>(?:19|20)\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})")
_NUMERICA = re.compile(r"(?<!\d)(?P<d>\d{1,2})[/.\-](?P<m>\d{1,2})[/.\-](?P<y>(?:19|20)\d{2})(?!\d)")
_ESTESA = re.compile(rf"(?<!\d)(?P<d>\d{{1,2}})(?:°|º)?\s+(?P<mese>{_MESI_RE})\s+(?P<y>(?:19|20)\d{{2}})(?!\d)", re.I)
_MESE_ANNO = re.compile(rf"(?P<mese>{_MESI_RE})[\s_\-]+(?P<y>(?:19|20)\d{{2}})(?!\d)", re.I)
_PDF_META = re.compile(r"D:(?P<y>(?:19|20)\d{2})(?P<m>\d{2})(?P<d>\d{2})")

# "Roma, 16 novembre 2026" / "Roma 16/11/2026" in chiusura dei comunicati.
_FIRMA = re.compile(
    rf"\bRoma,?\s+(?:li\s+|lì\s+)?(?P<data>\d{{1,2}}(?:°|º)?\s+(?:{_MESI_RE})\s+(?:19|20)\d{{2}}|\d{{1,2}}[/.]\d{{1,2}}[/.](?:19|20)\d{{2}})",
    re.I,
)
# "Circolare n. 123/XIX Sess./2024 del 15/03/2024" nelle prime righe.
_CIRCOLARE = re.compile(
    rf"circ(?:olare|\.)\s*(?:cni\s*)?n\.?\s*[\w/.\- ]{{1,40}}?\bdel\s+(?P<data>\d{{1,2}}[/.\-]\d{{1,2}}[/.\-](?:19|20)\d{{2}}|\d{{1,2}}(?:°|º)?\s+(?:{_MESI_RE})\s+(?:19|20)\d{{2}})",
    re.I,
)
# Anno della categoria delle notizie: /media-ing/news/230-2022/...
_ANNO_CATEGORIA = re.compile(r"/media-ing/[\w-]+/\d+-(?P<y>(?:19|20)\d{2})(?:/|$)")
# Anno come intero segmento o in coda a un segmento: /2022/, /area-covid-2020/
_ANNO_SEGMENTO = re.compile(r"(?:^|/|[-_])(?P<y>(?:19|20)\d{2})(?=/|$)")
_ANNO_FILE = re.compile(r"(?<![\d])(?P<y>(?:19|20)\d{2})(?![\d])")

_TIME_TAG = re.compile(r"<time[^>]*\bdatetime=[\"'](?P<v>[^\"']+)[\"']", re.I)
_ITEMPROP = re.compile(
    r"<meta[^>]*itemprop=[\"']date(?:Modified|Published)[\"'][^>]*content=[\"'](?P<v>[^\"']+)[\"']", re.I
)
_JSONLD = re.compile(r"\"date(?:Modified|Published)\"\s*:\s*\"(?P<v>[^\"]+)\"")


def _valida(y: int, m: int, d: int, oggi: date | None = None) -> date | None:
    oggi = oggi or date.today()
    if not (ANNO_MINIMO <= y <= oggi.year + 1):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str, oggi: date | None = None) -> date | None:
    """Prima data valida in `text`: ISO, gg/mm/aaaa (anche - e .), "16 novembre 2026", "D:AAAAMMGG"."""
    if not text:
        return None
    for regex in (_ISO, _PDF_META):
        m = regex.search(text)
        if m:
            found = _valida(int(m["y"]), int(m["m"]), int(m["d"]), oggi)
            if found:
                return found
    m = _NUMERICA.search(text)
    if m:
        found = _valida(int(m["y"]), int(m["m"]), int(m["d"]), oggi)
        if found:
            return found
    m = _ESTESA.search(text)
    if m:
        return _valida(int(m["y"]), MESI[m["mese"].lower()], int(m["d"]), oggi)
    return None


def _risultato(d: date, fonte: str, precisione: str) -> dict[str, str]:
    return {"date": d.isoformat(), "date_source": fonte, "date_precision": precisione}


def _anno(y: int, fonte: str, oggi: date | None) -> dict[str, str]:
    d = _valida(y, 7, 1, oggi)
    return _risultato(d, fonte, "year") if d else {}


def date_from_meta(meta: dict[str, Any], oggi: date | None = None) -> dict[str, str]:
    lower = {str(k).lower(): v for k, v in (meta or {}).items() if isinstance(v, str)}
    for key in META_KEYS:
        if key in lower:
            d = parse_date(lower[key], oggi)
            if d:
                return _risultato(d, f"meta:{key}", "day")
    return {}


def date_from_html(html: str, oggi: date | None = None) -> dict[str, str]:
    for regex, fonte in ((_ITEMPROP, "html:itemprop"), (_JSONLD, "html:json-ld"), (_TIME_TAG, "html:time")):
        m = regex.search(html or "")
        if m:
            d = parse_date(m["v"], oggi)
            if d:
                return _risultato(d, fonte, "day")
    return {}


def year_from_url(url: str, oggi: date | None = None) -> int | None:
    path = unquote(urlparse(url or "").path)
    m = _ANNO_CATEGORIA.search(path)
    if m:
        return int(m["y"])
    # Si escludono i nomi dei file: lo slug degli articoli inizia con un id numerico
    # ("/2017-titolo") che non e' un anno. I nomi dei PDF hanno una regola a parte.
    cartelle = path.rsplit("/", 1)[0] if "." in path.rsplit("/", 1)[-1] else path
    anni = [int(m["y"]) for m in _ANNO_SEGMENTO.finditer(cartelle)]
    anni = [a for a in anni if ANNO_MINIMO <= a <= (oggi or date.today()).year + 1]
    return anni[-1] if anni else None


def date_from_url(url: str, oggi: date | None = None) -> dict[str, str]:
    path = unquote(urlparse(url or "").path)
    nome = path.rsplit("/", 1)[-1]
    # Data completa nello slug: "345-13-11-2013-armando-zambrano-..."
    m = _NUMERICA.search(nome) if not nome.lower().endswith(".pdf") else None
    if m:
        d = _valida(int(m["y"]), int(m["m"]), int(m["d"]), oggi)
        if d:
            return _risultato(d, "url:slug", "day")
    anno = year_from_url(url, oggi)
    return _anno(anno, "url:anno", oggi) if anno else {}


def date_from_filename(url: str, oggi: date | None = None) -> dict[str, str]:
    nome = unquote(urlparse(url or "").path).rsplit("/", 1)[-1]
    nome = re.sub(r"\.pdf$", "", nome, flags=re.I)
    leggibile = nome.replace("_", " ")
    m = _NUMERICA.search(nome) or _ESTESA.search(leggibile)
    if m:
        d = parse_date(m.group(0), oggi)
        if d:
            return _risultato(d, "pdf:nome_file", "day")
    m = _MESE_ANNO.search(leggibile)
    if m:
        d = _valida(int(m["y"]), MESI[m["mese"].lower()], 15, oggi)
        if d:
            return _risultato(d, "pdf:nome_file", "month")
    anni = [int(x["y"]) for x in _ANNO_FILE.finditer(nome)]
    anni = [a for a in anni if ANNO_MINIMO <= a <= (oggi or date.today()).year + 1]
    return _anno(anni[-1], "pdf:nome_file", oggi) if anni else {}


def date_from_pdf_bytes(content: bytes, oggi: date | None = None) -> dict[str, str]:
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=content, filetype="pdf") as doc:
            meta = doc.metadata or {}
    except Exception as exc:  # PDF illeggibile: nessuna data, non e' un errore
        logger.debug(f"Metadati PDF non leggibili: {exc}")
        return {}
    for key in ("creationDate", "modDate"):
        d = parse_date(meta.get(key) or "", oggi)
        if d:
            return _risultato(d, f"pdf:{key}", "day")
    return {}


def date_from_text(text: str, url: str = "", oggi: date | None = None) -> dict[str, str]:
    """Date in posizioni riconoscibili del testo: intestazione di circolare, firma del comunicato."""
    testa = (text or "")[:1500]
    m = _CIRCOLARE.search(testa)
    if m:
        d = parse_date(m["data"], oggi)
        if d:
            return _risultato(d, "testo:circolare", "day")
    firme = list(_FIRMA.finditer(text or ""))
    if firme:
        d = parse_date(firme[-1]["data"], oggi)  # la firma e' in chiusura: vale l'ultima
        anno_url = year_from_url(url, oggi)
        if d and (anno_url is None or anno_url == d.year):
            return _risultato(d, "testo:firma", "day")
    return {}


def extract_document_date(document: dict[str, Any], raw_dir: str | Path | None = None,
                          oggi: date | None = None,
                          site_dates: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    """Data di un documento salvato dal crawler (JSON di Downloader), o {} se non ricavabile.

    `site_dates` e' la mappa URL -> data di pubblicazione letta dalla ricerca del
    sito (src/ingestion/site_dates.py): quando il documento c'e', vale quella.
    """
    meta = document.get("meta") or {}
    url = document.get("url") or meta.get("source") or ""
    is_pdf = meta.get("type") == "pdf" or url.lower().endswith(".pdf")
    base = Path(raw_dir) if raw_dir else None

    from src.ingestion.site_dates import lookup

    found = lookup(site_dates, url)
    if found:
        return found
    found = date_from_meta(meta, oggi)
    if not found and isinstance(document.get("raw_html"), str):
        # Documento appena scaricato e non ancora salvato (POST /ingest).
        found = date_from_html(document["raw_html"], oggi)
    if not found and base and meta.get("raw_html_path"):
        html_path = base / meta["raw_html_path"]
        if html_path.is_file():
            found = date_from_html(html_path.read_text(encoding="utf-8", errors="ignore"), oggi)
    if not found:
        found = date_from_text(document.get("content", ""), url, oggi)
    if not found and not is_pdf:
        found = date_from_url(url, oggi)
    if not found and is_pdf:
        found = date_from_filename(url, oggi)
        if not found and isinstance(document.get("raw_pdf"), str):
            import base64

            try:
                found = date_from_pdf_bytes(base64.b64decode(document["raw_pdf"]), oggi)
            except ValueError:
                found = {}
        if not found and base and meta.get("raw_pdf_path"):
            pdf_path = base / meta["raw_pdf_path"]
            if pdf_path.is_file():
                found = date_from_pdf_bytes(pdf_path.read_bytes(), oggi)
        if not found:
            found = date_from_url(url, oggi)
    return found


def load_document_dates(raw_dir: str | Path, oggi: date | None = None,
                        site_dates: dict[str, dict[str, str]] | None = None) -> dict[str, dict[str, str]]:
    """URL -> data per tutti i JSON in `raw_dir` (formato di Downloader.save_document)."""
    base = Path(raw_dir)
    dates: dict[str, dict[str, str]] = {}
    for path in sorted(base.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"Documento illeggibile {path.name}: {exc}")
            continue
        url = document.get("url") or (document.get("meta") or {}).get("source")
        if url:
            dates[url] = extract_document_date(document, base, oggi, site_dates)
    return dates
