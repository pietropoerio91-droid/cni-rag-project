"""Categorie dei percorsi nuovi della whitelist, invio a lotti e collection separata.

Le prove su Qdrant girano su una cartella temporanea in modalita' locale: non
toccano l'indice del progetto ne' richiedono modelli di embedding.
"""
import shutil
import tempfile

import pytest
from qdrant_client import QdrantClient

from src.governance.public_data_filter import PublicDataFilter
from src.vectorstore.bm25_sparse import SPARSE_VECTOR, collection_schema

BASE = "https://www.cni.it"


@pytest.mark.parametrize("path, attesa", [
    ("/area-cni/ordine-di-trento", "organi"),
    ("/sezioni-amministrazione-trasparente/bandi", "documenti"),
    ("/amministrazione-trasparente", "documenti"),
    ("/images/allegato-senza-sottocartella.pdf", "documenti"),
    ("/faq", "servizi"),
    ("/faq/domande-frequenti", "servizi"),
    ("/evidenza/articolo", "news"),
    ("/notizie-internazionali/x", "news"),
    ("/regolamento-sugli-accessi", "normativa"),
    ("/urp", "contatti"),
])
def test_i_percorsi_nuovi_della_whitelist_hanno_una_categoria(path, attesa):
    # contenuto neutro: senza la mappa dei percorsi finirebbe su "generico"
    assert PublicDataFilter().categorize(BASE + path, "testo neutro") == attesa


@pytest.mark.parametrize("path, attesa", [
    ("/cni/organi/consiglio", "organi"),
    ("/images/delibere/d1.pdf", "documenti"),
    ("/temi/faq-sismabonus", "temi"),          # "/faq" non ruba URL gia' categorizzati
    ("/media-ing/news/evidenza", "news"),
    ("/il-giornale-dell-ingegnere/articolo", "giornale"),
])
def test_gli_url_gia_categorizzati_non_cambiano(path, attesa):
    assert PublicDataFilter().categorize(BASE + path, "testo neutro") == attesa


def test_il_prefisso_deve_essere_un_segmento_intero():
    # "/urp" non deve coprire "/urpxyz"; senza parole chiave resta "generico"
    assert PublicDataFilter().categorize(BASE + "/urpxyz", "testo neutro") == "generico"


def test_la_sezione_it_resta_al_contenuto():
    assert PublicDataFilter().categorize(BASE + "/it/pagina", "calendario corso cfp formazione") == "formazione"


def _chunks(n):
    return [
        {"content": f"documento numero {i} sugli ingegneri", "embedding": [1.0, float(i)],
         "metadata": {"source": f"s{i}", "title": f"T{i}", "chunk_index": 0, "total_chunks": 1}}
        for i in range(n)
    ]


def _sparsi(client, name):
    punti, _ = client.scroll(name, limit=100, with_payload=True, with_vectors=True)
    return {p.payload["source"]: (tuple(p.vector[SPARSE_VECTOR].indices), tuple(p.vector[SPARSE_VECTOR].values))
            for p in punti}


def test_l_invio_a_lotti_da_gli_stessi_pesi_di_un_invio_unico(monkeypatch):
    from src.vectorstore import indexer as modulo

    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    for name in ("unico", "lotti"):
        c.create_collection(name, **collection_schema(dense_size=2))

    idx = modulo.VectorIndexer.__new__(modulo.VectorIndexer)
    monkeypatch.setattr(idx, "_get_client", lambda: c, raising=False)
    upserts = []
    originale = c.upsert
    monkeypatch.setattr(c, "upsert", lambda **kw: (upserts.append(len(kw["points"])), originale(**kw))[1])

    idx.collection_name = "unico"
    assert idx.index_chunks(_chunks(7), batch_size=100) == 7
    idx.collection_name = "lotti"
    assert idx.index_chunks(_chunks(7), batch_size=3) == 7

    assert upserts == [7, 3, 3, 1]
    # avgdl e' calcolata sull'intero corpus: i pesi BM25 non dipendono dai lotti
    assert _sparsi(c, "unico") == _sparsi(c, "lotti")
    c.close()
    shutil.rmtree(path, ignore_errors=True)


def test_una_collection_separata_non_tocca_quella_di_produzione(monkeypatch):
    from src.vectorstore import indexer as modulo_indexer
    from src.vectorstore import qdrant_client as modulo

    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    monkeypatch.setattr(
        modulo.ConfigLoader, "get_qdrant_config",
        classmethod(lambda cls: {"qdrant": {"vectors": {"size": 2, "distance": "Cosine"}}}),
    )
    manager = modulo.QdrantClientManager.__new__(modulo.QdrantClientManager)
    manager.client, manager.collection_name, manager.mode = c, "produzione", "local"
    manager._initialized = True
    manager.ensure_collection("produzione")
    monkeypatch.setattr(modulo.QdrantClientManager, "_instance", manager)
    monkeypatch.setattr(manager, "reinitialize", lambda: None)

    prod = modulo_indexer.VectorIndexer()
    prod.index_chunks(_chunks(3))

    nuova = modulo_indexer.VectorIndexer(collection_name="produzione_ingest_test")
    assert nuova.collection_name == "produzione_ingest_test"
    nuova.index_chunks(_chunks(5))
    nuova.clear_index()                       # svuota solo la propria collection
    nuova.index_chunks(_chunks(2))

    assert c.count("produzione").count == 3
    assert c.count("produzione_ingest_test").count == 2
    c.close()
    shutil.rmtree(path, ignore_errors=True)
