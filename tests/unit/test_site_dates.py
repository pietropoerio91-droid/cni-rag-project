from datetime import date

from src.ingestion import site_dates as sd
from src.ingestion.date_extractor import extract_document_date

OGGI = date(2026, 11, 20)


def _item(url, when):
    return (f'<li class="result__item"><p class="result__title"><a class="result__title-link" href="#">'
            f'<span class="result__title-text">T</span><span class="result__title-url">{url}</span></a></p>'
            f'<time class="result__date" datetime="{when}">x</time></li>')


def _page(items, total):
    return f'<div>Trovati {total} risultati</div><ol class="com-finder__results-list">{"".join(items)}</ol>'


def test_lettura_dei_risultati_della_ricerca():
    page = _page([_item("https://www.cni.it/media-ing/news/294-2026/5350-pompei", "2026-11-19T14:25:30+01:00"),
                  _item("https://www.cni.it/media-ing/news/x", "non-una-data")], 2)
    assert sd.parse_results(page) == [("https://www.cni.it/media-ing/news/294-2026/5350-pompei", "2026-11-19")]
    assert sd.total_results(page) == 2
    assert sd.total_results("<p>Trovati 2.555 risultati</p>") == 2555


def test_stessa_pagina_con_url_scritti_in_modo_diverso():
    a = sd.url_key("https://www.cni.it/media-ing/news/294-2026/5350-pompei/")
    assert a == sd.url_key("http://cni.it/media-ing/news/294-2026/5350-pompei")
    assert a != sd.url_key("https://www.cni.it/media-ing/news/294-2026/5351-altro")


def test_la_data_della_ricerca_ha_la_precedenza_sulle_euristiche():
    url = "https://www.cni.it/media-ing/news/137-2016/1720-ufficiale-zambrano-al-timone-del-cni-fino-al-2021"
    mappa = {sd.url_key(url): {"url": url, "date": "2016-12-15"}}
    doc = {"url": url, "content": "Roma, 3 marzo 2016", "meta": {"source": url}}
    assert extract_document_date(doc, oggi=OGGI, site_dates=mappa) == {
        "date": "2016-12-15", "date_source": "sito:ricerca", "date_precision": "day"}
    # Senza mappa restano le euristiche di prima.
    assert extract_document_date(doc, oggi=OGGI)["date_source"] != "sito:ricerca"


class _Risposta:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _ClientFinto:
    """Ricerca con 250 risultati: pagine da 100, 97 (risultati incompleti a meta' elenco) e 50."""

    def __init__(self):
        self.calls = []

    def get(self, url, params):
        self.calls.append(params)
        start = params["start"]
        n = {0: 100, 100: 97, 200: 50}.get(start, 0)
        items = [_item(f"https://www.cni.it/media-ing/news/{params['q']}/{start + i}", "2024-05-0" + str(1 + i % 9))
                 for i in range(n)]
        return _Risposta(_page(items, 250))


def test_si_scorrono_tutte_le_pagine_fino_al_totale():
    client = _ClientFinto()
    dates = sd.fetch_site_dates(terms=("a",), delay=0, client=client)
    assert [c["start"] for c in client.calls] == [0, 100, 200]
    assert len(dates) == 247


def test_salvataggio_e_lettura(tmp_path):
    path = sd.save_site_dates({"cni.it/media-ing/news/x": {"url": "https://www.cni.it/media-ing/news/x", "date": "2020-01-02"}}, tmp_path / "d.json")
    assert sd.load_site_dates(path) == {"cni.it/media-ing/news/x": {"url": "https://www.cni.it/media-ing/news/x", "date": "2020-01-02"}}
    assert sd.load_site_dates(tmp_path / "manca.json") == {}


def test_pagine_istituzionali_restano_senza_data(tmp_path):
    news = "https://www.cni.it/media-ing/news/230-2022/4192-eletti-i-nuovi-vertici"
    consiglio = "https://www.cni.it/cni/consiglio"
    path = sd.save_site_dates({sd.url_key(news): {"url": news, "date": "2022-12-07"},
                               sd.url_key(consiglio): {"url": consiglio, "date": "2016-05-26"}}, tmp_path / "d.json")
    mappa = sd.load_site_dates(path)
    assert sd.lookup(mappa, news)["date"] == "2022-12-07"
    assert sd.lookup(mappa, consiglio) == {}
    # Una sezione aggiunta in configurazione vale senza riscaricare la mappa.
    assert sd.lookup(sd.load_site_dates(path, ("/media-ing", "/cni")), consiglio)["date"] == "2016-05-26"
    assert not sd.in_dated_section("https://www.cni.it/media-ingegneria/x")
