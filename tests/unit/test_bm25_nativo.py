"""Il BM25 nativo di Qdrant deve dare gli stessi punteggi del BM25 in memoria."""
import shutil
import tempfile

import pytest
from qdrant_client import QdrantClient, models

from src.rag.sparse_index import BM25Index
from src.vectorstore.bm25_sparse import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    document_vector,
    indexed_text,
    query_vector,
    term_index,
    tokenize,
)

DOCS = [
    {"title": "Consiglio", "content": "Il presidente del CNI è Angelo Domenico Perrini", "source": "s0", "chunk_index": 0},
    {"title": "Contatti", "content": "Codice fiscale 80057570584 del Consiglio Nazionale degli Ingegneri", "source": "s1", "chunk_index": 0},
    {"title": "Formazione", "content": "Corsi di aggiornamento professionale per gli ingegneri", "source": "s2", "chunk_index": 0},
    {"title": "Ordini", "content": "Elenco degli ordini provinciali di Trento e Bolzano", "source": "s3", "chunk_index": 0},
]


@pytest.fixture(scope="module")
def client():
    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    tokens = [tokenize(indexed_text(d)) for d in DOCS]
    avgdl = sum(map(len, tokens)) / len(tokens)
    c.create_collection(
        "t",
        vectors_config={DENSE_VECTOR: models.VectorParams(size=2, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    c.upsert("t", points=[
        models.PointStruct(id=i, vector={DENSE_VECTOR: [1.0, float(i)], SPARSE_VECTOR: document_vector(tk, avgdl)}, payload=d)
        for i, (d, tk) in enumerate(zip(DOCS, tokens))
    ])
    yield c
    c.close()
    shutil.rmtree(path, ignore_errors=True)


@pytest.mark.parametrize("query", [
    "codice fiscale del CNI 80057570584",
    "chi è il presidente Perrini",
    "ordini provinciali Trento",
    "università",  # nessun documento la contiene
])
def test_punteggi_uguali_al_bm25_in_memoria(client, query):
    memoria = {d["source"]: d["score"] for d in BM25Index(DOCS, include_title=True).retrieve(query, top_k=10)}
    nativo = {
        p.payload["source"]: p.score
        for p in client.query_points("t", query=query_vector(query), using=SPARSE_VECTOR, limit=10, with_payload=True).points
        if p.score > 0
    }
    assert nativo.keys() == memoria.keys()
    for source, score in memoria.items():
        assert nativo[source] == pytest.approx(score, rel=1e-5)


def test_il_codice_fiscale_si_trova(client):
    primo = client.query_points("t", query=query_vector("80057570584"), using=SPARSE_VECTOR, limit=1, with_payload=True).points[0]
    assert primo.payload["source"] == "s1"


def test_indice_stabile_e_indipendente_dal_processo():
    assert term_index("consiglio") == term_index("consiglio")
    assert 0 <= term_index("consiglio") < 2**32


def test_i_pesi_dei_termini_collidenti_si_sommano(monkeypatch):
    from src.vectorstore import bm25_sparse
    monkeypatch.setattr(bm25_sparse, "term_index", lambda t: 7)
    vec = bm25_sparse.query_vector("alfa beta")
    assert vec.indices == [7] and vec.values == [2.0]
