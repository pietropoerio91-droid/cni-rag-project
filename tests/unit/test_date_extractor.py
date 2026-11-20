import base64
import json
from datetime import date

from src.ingestion import date_extractor as de

OGGI = date(2026, 11, 20)


def _doc(url, content="", meta=None, **extra):
    return {"url": url, "content": content, "meta": {"source": url, **(meta or {})}, **extra}


def test_formati_di_data():
    assert de.parse_date("2022-11-15T10:00:00+01:00") == date(2022, 11, 15)
    assert de.parse_date("15/03/2024") == date(2024, 3, 15)
    assert de.parse_date("Roma 16 novembre 2026") == date(2026, 11, 16)
    assert de.parse_date("D:20230315120000+01'00'") == date(2023, 3, 15)
    assert de.parse_date("31/02/2024") is None
    assert de.parse_date("nessuna data") is None


def test_anno_futuro_o_troppo_vecchio_non_e_una_data():
    assert de.parse_date("15/03/2031", OGGI) is None
    assert de.parse_date("15/03/1950", OGGI) is None


def test_anno_della_categoria_delle_notizie():
    url = "https://www.cni.it/media-ing/news/230-2022/4192-eletti-i-nuovi-vertici-del-consiglio-nazionale-ingegneri"
    assert de.extract_document_date(_doc(url), oggi=OGGI) == {
        "date": "2022-07-01", "date_source": "url:anno", "date_precision": "year"}


def test_l_id_dell_articolo_non_e_scambiato_per_un_anno():
    url = "https://www.cni.it/media-ing/news/190-2017/2060-annuncio-delrio"
    assert de.extract_document_date(_doc(url), oggi=OGGI)["date"] == "2017-07-01"
    url = "https://www.cni.it/media-ing/news/230-2022/2017-titolo-con-numero"
    assert de.extract_document_date(_doc(url), oggi=OGGI)["date"] == "2022-07-01"


def test_data_completa_nello_slug():
    url = "https://www.cni.it/media-ing/news/135-2013/345-13-11-2013-armando-zambrano-presidente"
    got = de.extract_document_date(_doc(url), oggi=OGGI)
    assert (got["date"], got["date_source"], got["date_precision"]) == ("2013-11-13", "url:slug", "day")


def test_firma_del_comunicato_coerente_con_l_url():
    url = "https://www.cni.it/media-ing/news/294-2026/5345-ppp-il-cni"
    testo = "Il CNI chiede un tavolo tecnico.\nRoma 16 novembre 2026\nComunicato stampa"
    got = de.extract_document_date(_doc(url, testo), oggi=OGGI)
    assert (got["date"], got["date_source"]) == ("2026-11-16", "testo:firma")


def test_firma_in_contrasto_con_l_url_vale_l_anno_dell_url():
    url = "https://www.cni.it/media-ing/news/294-2026/5345-ppp-il-cni"
    testo = "Come ricordato a Roma, 3 marzo 2019, il Consiglio..."
    assert de.extract_document_date(_doc(url, testo), oggi=OGGI)["date_source"] == "url:anno"


def test_pagina_istituzionale_con_date_di_nascita_resta_senza_data():
    testo = ("Angelo Domenico Perrini Presidente Nato ad Alberobello (Ba) il 15/01/1948. "
             "Presidente dal 12 marzo 2014 al 20 febbraio 2018.")
    assert de.extract_document_date(_doc("https://www.cni.it/cni/consiglio", testo), oggi=OGGI) == {}


def test_intestazione_di_circolare():
    testo = "CONSIGLIO NAZIONALE DEGLI INGEGNERI\nCirc. n. 123/XX Sess./2024 del 15/03/2024\nOggetto: ..."
    got = de.extract_document_date(_doc("https://cni-online.it/circolari/123", testo), oggi=OGGI)
    assert (got["date"], got["date_source"]) == ("2024-03-15", "testo:circolare")


def test_nome_del_file_pdf():
    meta = {"type": "pdf"}
    got = de.extract_document_date(_doc("https://www.cni.it/images/1_Newsletter_3_-_gennaio_2023.pdf", meta=meta), oggi=OGGI)
    assert (got["date"], got["date_precision"]) == ("2023-01-15", "month")
    got = de.extract_document_date(_doc("https://www.cni.it/images/IF/VERBALE_IF_23-05-2023.pdf", meta=meta), oggi=OGGI)
    assert (got["date"], got["date_precision"]) == ("2023-05-23", "day")


def test_metadati_interni_del_pdf():
    import fitz

    pdf = fitz.open()
    pdf.new_page()
    pdf.set_metadata({"creationDate": "D:20210610090000+02'00'"})
    raw = base64.b64encode(pdf.tobytes()).decode("ascii")
    doc = _doc("https://www.cni.it/images/documento.pdf", meta={"type": "pdf"}, raw_pdf=raw)
    got = de.extract_document_date(doc, oggi=OGGI)
    assert (got["date"], got["date_source"]) == ("2021-06-10", "pdf:creationDate")


def test_metadati_html_hanno_la_precedenza():
    meta = {"article:published_time": "2020-05-04T08:00:00Z"}
    url = "https://www.cni.it/media-ing/news/230-2022/1-x"
    assert de.extract_document_date(_doc(url, meta=meta), oggi=OGGI)["date"] == "2020-05-04"
    html = '<article><time datetime="2019-09-30">30 settembre</time></article>'
    assert de.extract_document_date(_doc(url, raw_html=html), oggi=OGGI)["date_source"] == "html:time"


def test_lettura_dei_file_salvati_dal_crawler(tmp_path):
    (tmp_path / "html").mkdir()
    (tmp_path / "html" / "a.html").write_text('<script type="application/ld+json">{"datePublished": "2018-02-01"}</script>')
    docs = {
        "a.json": _doc("https://www.cni.it/temi/a", meta={"raw_html_path": "html/a.html"}),
        "b.json": _doc("https://www.cni.it/cni/consiglio"),
    }
    for name, doc in docs.items():
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    dates = de.load_document_dates(tmp_path, oggi=OGGI)
    assert dates["https://www.cni.it/temi/a"]["date"] == "2018-02-01"
    assert dates["https://www.cni.it/cni/consiglio"] == {}


def test_nessuna_data_di_pubblicazione_nel_futuro():
    pdf = {"type": "pdf"}
    # Periodo nel nome del file: si prende l'anno piu' recente non futuro.
    got = de.extract_document_date(_doc("https://www.cni.it/images/Piano_triennale_2025-2027.pdf", meta=pdf), oggi=OGGI)
    assert got["date"] == "2025-07-01"
    assert de.extract_document_date(_doc("https://www.cni.it/images/Bilancio_preventivo_2027.pdf", meta=pdf), oggi=OGGI) == {}
    assert de.parse_date("Roma, 16 dicembre 2026", OGGI) is None
    assert de.parse_date("Roma, 16 novembre 2026", OGGI) is not None


def test_anno_corrente_prima_di_luglio_vale_oggi():
    url = "https://www.cni.it/media-ing/news/294-2026/5000-x"
    assert de.extract_document_date(_doc(url), oggi=date(2026, 3, 10))["date"] == "2026-03-10"
    assert de.extract_document_date(_doc(url), oggi=OGGI)["date"] == "2026-07-01"
