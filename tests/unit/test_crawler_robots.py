from urllib.robotparser import RobotFileParser

from src.ingestion.crawler import CNICrawler

ROBOTS = """User-agent: *
Disallow: /administrator/
Disallow: /cache/
"""


def _crawler(robots_text=None, included=("/media-ing", "/cache")):
    c = CNICrawler.__new__(CNICrawler)
    c.allowed_domains = ["www.cni.it", "cni.it"]
    c.included_paths = list(included)
    c._robots = None
    if robots_text is not None:
        c._robots = RobotFileParser()
        c._robots.parse(robots_text.splitlines())
    return c


def test_un_percorso_vietato_da_robots_non_viene_visitato():
    c = _crawler(ROBOTS)
    assert not c._is_allowed("https://www.cni.it/cache/pagina")


def test_un_percorso_permesso_resta_permesso():
    assert _crawler(ROBOTS)._is_allowed("https://www.cni.it/media-ing/news")


def test_senza_robots_letto_vale_solo_il_resto_dei_filtri():
    # robots non caricato (opzione spenta o file irraggiungibile): nessun blocco da robots
    assert _crawler(None)._is_allowed("https://www.cni.it/cache/pagina")


def test_i_permessi_della_whitelist_restano_in_vigore():
    assert not _crawler(ROBOTS)._is_allowed("https://www.cni.it/altro/percorso")
