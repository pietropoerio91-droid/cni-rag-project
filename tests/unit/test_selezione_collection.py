"""Scelta della collection attiva dal frontend (GET /collections, PUT /collections/active).

Qdrant gira su una cartella temporanea e il YAML e' una copia: le prove non
toccano l'indice ne' la configurazione del progetto.
"""
import shutil
import tempfile

import pytest
from qdrant_client import QdrantClient, models

from src.vectorstore import qdrant_client as modulo
from src.vectorstore.bm25_sparse import collection_schema

YAML = """qdrant:
  mode: local
  path: ./data/qdrant_db
  # commento da conservare
  collection_name: produzione
  vectors:
    size: 2
"""


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    c.create_collection("produzione", **collection_schema(dense_size=2))
    c.create_collection("nuova", **collection_schema(dense_size=2))
    c.create_collection("dimensione_diversa", **collection_schema(dense_size=3))
    c.create_collection("solo_densa", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))

    yaml_path = tmp_path / "qdrant_config.yaml"
    yaml_path.write_text(YAML, encoding="utf-8")
    monkeypatch.setattr(modulo, "QDRANT_CONFIG_PATH", yaml_path)
    config = {"qdrant": {"collection_name": "produzione", "vectors": {"size": 2, "distance": "Cosine"}}}
    monkeypatch.setattr(modulo.ConfigLoader, "get_qdrant_config", classmethod(lambda cls: config))

    manager = modulo.QdrantClientManager.__new__(modulo.QdrantClientManager)
    manager.client, manager.collection_name, manager.mode = c, "produzione", "local"
    manager._initialized = True
    monkeypatch.setattr(modulo.QdrantClientManager, "_instance", manager)

    yield manager, yaml_path, config
    c.close()
    shutil.rmtree(path, ignore_errors=True)


def test_l_elenco_segnala_attiva_e_compatibili(ambiente):
    manager, _, _ = ambiente
    info = {c["name"]: c for c in manager.list_collections()}

    assert info["produzione"]["active"] and info["produzione"]["compatible"]
    assert info["nuova"]["compatible"] and not info["nuova"]["active"]
    assert not info["dimensione_diversa"]["compatible"]
    assert "3 dimensioni" in info["dimensione_diversa"]["incompatible_reason"]
    assert not info["solo_densa"]["compatible"]


def test_il_cambio_vale_per_retriever_indicizzatore_e_yaml(ambiente):
    from src.vectorstore.indexer import VectorIndexer
    from src.vectorstore.retriever import VectorRetriever

    manager, yaml_path, config = ambiente
    retriever = VectorRetriever(embedding_model=None)
    indexer = VectorIndexer()
    assert retriever.collection_name == indexer.collection_name == "produzione"

    manager.set_active_collection("nuova")

    # oggetti gia' creati (la catena RAG e' in cache nell'API) seguono il cambio
    assert retriever.collection_name == indexer.collection_name == "nuova"
    assert config["qdrant"]["collection_name"] == "nuova"
    testo = yaml_path.read_text(encoding="utf-8")
    assert "  collection_name: nuova\n" in testo
    assert "# commento da conservare" in testo      # il resto del file resta com'e'
    assert testo.replace("nuova", "produzione") == YAML


@pytest.mark.parametrize("nome, errore", [
    ("inesistente", "non esiste"),
    ("dimensione_diversa", "non e' utilizzabile"),
    ("solo_densa", "non e' utilizzabile"),
])
def test_collection_inesistenti_o_incompatibili_sono_rifiutate(ambiente, nome, errore):
    manager, yaml_path, _ = ambiente
    with pytest.raises(ValueError, match=errore):
        manager.set_active_collection(nome)
    assert manager.collection_name == "produzione"
    assert yaml_path.read_text(encoding="utf-8") == YAML


def test_endpoint_elenco_e_cambio(ambiente, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import routes
    from src.vectorstore.indexer import VectorIndexer

    monkeypatch.setattr(routes, "_vector_indexer", VectorIndexer())
    monkeypatch.setitem(routes._ingest_status, "running", False)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    client = TestClient(app)

    res = client.get("/api/v1/collections").json()
    assert res["active"] == "produzione" and len(res["collections"]) == 4

    assert client.put("/api/v1/collections/active", json={"name": "solo_densa"}).status_code == 400

    monkeypatch.setitem(routes._ingest_status, "running", True)
    assert client.put("/api/v1/collections/active", json={"name": "nuova"}).status_code == 409

    monkeypatch.setitem(routes._ingest_status, "running", False)
    ok = client.put("/api/v1/collections/active", json={"name": "nuova"})
    assert ok.status_code == 200 and ok.json()["previous"] == "produzione"
    assert client.get("/api/v1/collections").json()["active"] == "nuova"


def test_prova_completa_indicizzazione_su_collection_nuova_e_attivazione(ambiente, monkeypatch, tmp_path):
    """Il flusso vero di POST /ingest, con crawler ed embedding finti: crea una
    collection nuova, lascia intatta la produzione, e la nuova si attiva dopo."""
    import asyncio

    from src.api import routes
    from src.ingestion import crawler, downloader, embedder
    from src.vectorstore.indexer import VectorIndexer

    manager, yaml_path, _ = ambiente
    VectorIndexer().index_chunks([
        {"content": "vecchio", "embedding": [1.0, 0.0], "metadata": {"source": "v"}}
    ])

    # Testo vario: un testo ripetuto verrebbe scartato (giustamente) dal controllo qualita'.
    testo = (
        "Il Consiglio Nazionale degli Ingegneri coordina gli ordini provinciali presenti sul territorio.\n"
        "Ogni scheda riporta la sede, i contatti della segreteria, gli orari di apertura e il presidente.\n"
        "Le informazioni sono aggiornate periodicamente dagli uffici e consultabili da tutti i cittadini."
    )
    pagine = [
        {"url": "https://www.cni.it/area-cni/ordine-di-trento", "content": testo, "meta": {"title": "Trento"}},
        {"url": "https://www.cni.it/faq", "content": "Domande frequenti. " + testo, "meta": {"title": "FAQ"}},
    ]

    async def crawl_finto(self):
        return pagine

    monkeypatch.setattr(crawler.CNICrawler, "crawl", crawl_finto)
    monkeypatch.setattr(downloader.Downloader, "__init__", lambda self, output_dir=None: setattr(self, "output_dir", tmp_path))
    monkeypatch.setattr(embedder.EmbeddingGenerator, "__init__", lambda self, embedding_model=None: None)
    monkeypatch.setattr(embedder.EmbeddingGenerator, "process_chunks",
                        lambda self, chunks: [{**c, "embedding": [0.5, 0.5]} for c in chunks])
    monkeypatch.setattr(routes, "_vector_indexer", VectorIndexer())
    monkeypatch.setattr(routes, "_ingest_status", dict(routes._ingest_status, running=False))

    async def lancia_e_attendi():
        await routes.ingest()
        for _ in range(200):
            await asyncio.sleep(0.05)
            if routes._ingest_status["phase"] in ("done", "error"):
                break

    asyncio.run(lancia_e_attendi())
    stato = routes._ingest_status
    assert stato["phase"] == "done", stato["message"]

    nuova = stato["collection"]
    assert nuova.startswith("produzione_ingest_")
    assert manager.client.count("produzione").count == 1          # produzione intatta
    assert manager.client.count(nuova).count == stato["chunks_indexed"] > 0
    assert manager.collection_name == "produzione"                # nessun cambio automatico

    categorie = {p.payload["source"]: p.payload["category"]
                 for p in manager.client.scroll(nuova, limit=100, with_payload=True)[0]}
    assert categorie == {"https://www.cni.it/area-cni/ordine-di-trento": "organi",
                         "https://www.cni.it/faq": "servizi"}

    manager.set_active_collection(nuova)
    assert f"collection_name: {nuova}" in yaml_path.read_text(encoding="utf-8")
    assert routes.get_vector_indexer().count_points() == stato["chunks_indexed"]
