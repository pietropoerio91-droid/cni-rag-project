import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DENIED_KEYWORDS = [
    "credenziali",
    "non-pubblico",
    "riservato",
]

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "news": [
        "/media-ing/news", "/news", "/comunicati-stampa", "/rassegna-stampa",
        "/media-ing/multimedia", "/media-ing/area-covid",
        "/media-ing/comunicati-speciali", "/media-ing/newsletter",
    ],
    "documenti": [
        "/documenti", "/atti", "/images/atti", "/images/bilanci",
        "/images/delibere", "/images/verbali", "/images/pubblicazioni",
        "/images/modulistica",
    ],
    "normativa": [
        "/normativa", "/decreti", "/leggi", "/regolamenti",
        "/images/normativa", "/images/atti_generali",
        "/cni/codice-deontologico", "/cni/carta-ecoetica",
    ],
    "formazione": [
        "/formazione", "/corsi", "/crediti", "/cfp",
        "/scuola-formazione", "/images/formazione",
        "/cni/scuola-di-formazione",
    ],
    "commissioni": [
        "/commissioni", "/comitati", "/gruppi-lavoro",
        "/images/commissioni", "/cni/federazioni-e-consulte",
    ],
    "organi": [
        "/organi", "/consiglio", "/presidenza", "/cni/organi",
        "/cni/ordini-provinciali", "/cni/elezione-ordini-provinciali",
        "/cni/consigli-di-disciplina", "/cni/assemblea-presidenti",
        "/cni/fondazione", "/cni/c3i",
        "/cni/struttura-tecnica-nazionale",
    ],
    "servizi": [
        "/servizi", "/sportello", "/convenzioni", "/images/servizi",
        "/cni/agenzia-certing",
    ],
    "eventi": [
        "/eventi", "/convegni", "/seminari",
        "/media-ing/atti-eventi-cni",
    ],
    "temi": [
        "/temi", "/sicurezza", "/ambiente", "/energia",
        "/costruzioni", "/innovazione", "/professione",
        "/opere-portuali", "/ingegneri-triennali",
        "/ingenio-al-femminile", "/area-giurisdizionale",
        "/informatica-e-telecomunicazioni",
        "/libera-professione-e-societa-di-ingegneria",
        "/cni/centro-studi-urbanistici",
    ],
    "giornale": [
        "/il-giornale-dell-ingegnere", "/giornale-ingegnere",
        "/l-ingegnere-italiano",
    ],
    "albo": [
        "/albo", "/elenchi", "/iscrizione", "/registro",
        "/albo-unico",
    ],
    "contatti": [
        "/contatti", "/contatta", "/sede",
    ],
    "chi_siamo": [
        "/chi-siamo", "/cni/chi-siamo",
        "/cni/centro-studi",
        "/cni/immagine-cni",
    ],
}


# Percorsi aggiunti alla whitelist del crawler il 21/09 (config/rag_config.yaml,
# `included_paths`) che nessuna voce di CATEGORY_PATTERNS copre. Si confrontano
# come prefisso del path e solo dopo CATEGORY_PATTERNS: un URL che oggi riceve una
# categoria dai pattern la conserva identica, e solo le pagine che finivano sulla
# categoria dedotta dal contenuto ne ricevono una dal percorso.
# `/it/` (sezione internazionale) resta di proposito al contenuto: raccoglie
# pagine di argomento troppo vario per una sola categoria.
WHITELIST_PATH_CATEGORIES: dict[str, list[str]] = {
    "organi": [
        "/area-cni",                    # schede territoriali degli ordini provinciali
        "/network-cni", "/rete-internazionale", "/ingegneri-e-rappresentanza",
    ],
    "documenti": [
        "/sezioni-amministrazione-trasparente", "/amministrazione-trasparente",
        "/pubblicazioni-cni", "/note-legali", "/privacy-cookies",
        "/images",                      # PDF fuori dalle sottocartelle gia' mappate
    ],
    "normativa": [
        "/regolamento-sugli-accessi",
        "/nuovo-codice-deontologico-degli-ingegneri-italiani",
        "/bonus-110-chiarimenti-commissione-csllpp",
    ],
    "news": [
        "/evidenza", "/notizie-internazionali",
    ],
    "servizi": [
        "/faq", "/opportunita", "/whistleblowing", "/euring",
        "/riconoscimento-qualifiche-in-italia",
    ],
    "temi": [
        "/ingegneri-in-italia", "/ingegneri-biomedici-e-clinici",
    ],
    "contatti": [
        "/urp",
    ],
}


def _path_matches(path: str, prefix: str) -> bool:
    """Prefisso di percorso intero: `/urp` copre `/urp` e `/urp/...`, non `/urpxyz`."""
    return path == prefix or path.startswith(prefix + "/")


CONTENT_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "news": ["comunicato stampa", "rassegna stampa", "notizia", "news", "aggiornamento"],
    "normativa": ["legge", "decreto", "regolamento", "normativa", "articolo", "codice"],
    "formazione": ["corso", "credito", "cfp", "formazione", "seminario", "workshop"],
    "organi": ["consiglio", "presidente", "vicepresidente", "segretario", "ordine"],
    "commissioni": ["commissione", "comitato", "gruppo di lavoro"],
    "servizi": ["servizio", "sportello", "convenzione", "modulistica", "domanda"],
    "documenti": ["documento", "bilancio", "relazione", "verbale", "delibera"],
    "eventi": ["evento", "convegno", "seminario", "conferenza"],
    "temi": ["sicurezza", "ambiente", "energia", "innovazione", "professione"],
    "albo": ["albo", "elenco", "iscrizione", "registro", "ingegnere"],
    "contatti": ["contatto", "sede", "telefono", "email", "pec", "indirizzo"],
    "chi_siamo": ["chi siamo", "fondazione", "mission", "storia", "cni"],
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
        path = urlparse(url_lower).path.rstrip("/")
        for category, prefixes in WHITELIST_PATH_CATEGORIES.items():
            if any(_path_matches(path, p) for p in prefixes):
                return category
        content_lower = content.lower()
        best_cat = "generico"
        best_score = 0
        for category, keywords in CONTENT_CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > best_score:
                best_score = score
                best_cat = category
        return best_cat
