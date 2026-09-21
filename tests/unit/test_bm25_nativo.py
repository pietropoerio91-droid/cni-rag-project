"""BM25 nativo in Qdrant: correttezza del punteggio e flusso del recupero ibrido.

Le prove girano su una collection temporanea in modalita' locale: non toccano
l'indice del progetto ne' richiedono modelli di embedding.
"""
import math
import shutil
import tempfile
from collections import Counter

import pytest
from qdrant_client import QdrantClient, models

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
# Il documento s1 e' ortogonale alla domanda densa: solo il canale lessicale puo' trovarlo.
DENSE = {"s0": [1.0, 0.1], "s1": [0.0, 1.0], "s2": [0.9, 0.3], "s3": [0.8, 0.2]}
K1, B = 1.2, 0.75


def reference_bm25(docs, query):
    """BM25 con IDF alla Lucene, scritto per esteso: il riferimento contro cui si controlla Qdrant."""
    tokens = [tokenize(indexed_text(d)) for d in docs]
    n, avgdl = len(docs), sum(map(len, tokens)) / len(docs)
    df = Counter(t for tk in tokens for t in set(tk))
    scores = {}
    for doc, tk in zip(docs, tokens):
        tf, score = Counter(tk), 0.0
        for t in tokenize(query):
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * len(tk) / avgdl))
        if score > 0:
            scores[doc["source"]] = score
    return scores


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
        models.PointStruct(id=i, vector={DENSE_VECTOR: DENSE[d["source"]], SPARSE_VECTOR: document_vector(tk, avgdl, K1, B)}, payload=d)
        for i, (d, tk) in enumerate(zip(DOCS, tokens))
    ])
    yield c
    c.close()
    shutil.rmtree(path, ignore_errors=True)


# --- tokenizzatore ---------------------------------------------------------

def test_le_cifre_restano_cercabili():
    assert "80057570584" in tokenize("Codice fiscale 80057570584")


def test_gli_accenti_non_cambiano_il_termine():
    assert tokenize("università") == tokenize("universita") == ["universita"]


def test_minuscole_e_token_di_almeno_due_caratteri():
    assert tokenize("A CNI e il Presidente") == ["cni", "il", "presidente"]


def test_testo_vuoto():
    assert tokenize("") == [] and tokenize(None) == []


def test_il_titolo_entra_nel_testo_indicizzato():
    assert "consiglio" in tokenize(indexed_text({"title": "Consiglio", "content": "altro"}))
    assert "consiglio" not in tokenize(indexed_text({"title": "Consiglio", "content": "altro"}, include_title=False))


# --- vettori sparsi --------------------------------------------------------

def test_indice_stabile_e_u32():
    assert term_index("consiglio") == term_index("consiglio")
    assert 0 <= term_index("consiglio") < 2**32


def test_i_pesi_dei_termini_collidenti_si_sommano(monkeypatch):
    from src.vectorstore import bm25_sparse
    monkeypatch.setattr(bm25_sparse, "term_index", lambda t: 7)
    vec = bm25_sparse.query_vector("alfa beta")
    assert vec.indices == [7] and vec.values == [2.0]


def test_la_domanda_conta_i_termini_ripetuti():
    vec = query_vector("codice fiscale codice")
    assert sorted(vec.values) == [1.0, 2.0]


# --- punteggio in Qdrant ---------------------------------------------------

@pytest.mark.parametrize("query", [
    "codice fiscale del CNI 80057570584",
    "chi è il presidente Perrini",
    "ordini provinciali Trento",
    "università",  # nessun documento la contiene
])
def test_punteggi_uguali_al_riferimento(client, query):
    atteso = reference_bm25(DOCS, query)
    trovato = {
        p.payload["source"]: p.score
        for p in client.query_points("t", query=query_vector(query), using=SPARSE_VECTOR, limit=10, with_payload=True).points
        if p.score > 0
    }
    assert trovato.keys() == atteso.keys()
    for source, score in atteso.items():
        assert trovato[source] == pytest.approx(score, rel=1e-5)


def test_il_codice_fiscale_si_trova(client):
    primo = client.query_points("t", query=query_vector("80057570584"), using=SPARSE_VECTOR, limit=1, with_payload=True).points[0]
    assert primo.payload["source"] == "s1"


# --- HybridRetriever -------------------------------------------------------

class _Manager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


class _Embedding:
    def embed_query(self, text):
        return [1.0, 0.0]


class _DenseRetriever:
    """Ricerca densa finta: restituisce cio' che il canale denso puo' trovare."""
    collection_name = "t"
    score_threshold = 0.3
    embedding_model = _Embedding()

    def __init__(self, client):
        self.manager = _Manager(client)

    def retrieve(self, query, top_k, filter_condition=None):
        out = self.manager.get_client().query_points(
            "t", query=[1.0, 0.0], using=DENSE_VECTOR, limit=top_k, score_threshold=self.score_threshold, with_payload=True
        ).points
        return [dict(p.payload, score=p.score) for p in out]


def _retriever(client, enabled):
    from src.rag.hybrid_retriever import HybridRetriever
    r = HybridRetriever.__new__(HybridRetriever)
    r.vector_retriever = _DenseRetriever(client)
    r.query_classifier = type("C", (), {"classify": staticmethod(lambda q: "generico")})()
    r.top_k, r.dense_top_k, r.sparse_top_k, r.rrf_k = 25, 50, 50, 60
    r.hybrid_enabled, r.category_filter = enabled, False
    return r


def test_senza_ibrido_il_canale_lessicale_non_interviene(client):
    fonti = {d["source"] for d in _retriever(client, False).retrieve("codice fiscale 80057570584")}
    assert "s1" not in fonti


def test_con_ibrido_il_lessicale_porta_dentro_cio_che_il_denso_manca(client):
    fonti = [d["source"] for d in _retriever(client, True).retrieve("codice fiscale 80057570584")]
    assert "s1" in fonti


def test_il_risultato_ha_la_forma_attesa_dal_resto_della_pipeline(client):
    doc = _retriever(client, True).retrieve("codice fiscale 80057570584")[0]
    assert set(doc) == {"content", "source", "title", "score", "chunk_index", "category"}


def test_top_k_limita_i_candidati(client):
    assert len(_retriever(client, True).retrieve("ingegneri consiglio", top_k=2)) <= 2


# --- indicizzazione --------------------------------------------------------

def _chunks():
    return [
        {"content": d["content"], "embedding": DENSE[d["source"]],
         "metadata": {"source": d["source"], "title": d["title"], "chunk_index": 0, "total_chunks": 1}}
        for d in DOCS
    ] + [{"content": "senza embedding", "metadata": {"source": "x"}}]


def test_lo_schema_condiviso_ha_denso_e_sparso_con_idf():
    from src.vectorstore.bm25_sparse import collection_schema
    schema = collection_schema(dense_size=4)
    assert schema["vectors_config"][DENSE_VECTOR].size == 4
    assert schema["sparse_vectors_config"][SPARSE_VECTOR].modifier == models.Modifier.IDF


def test_l_indicizzatore_scrive_denso_e_sparso_e_salta_i_chunk_senza_embedding(monkeypatch):
    from src.vectorstore import indexer as modulo
    from src.vectorstore.bm25_sparse import collection_schema

    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    c.create_collection("idx", **collection_schema(dense_size=2))

    indexer = modulo.VectorIndexer.__new__(modulo.VectorIndexer)
    indexer.collection_name = "idx"
    monkeypatch.setattr(indexer, "_get_client", lambda: c, raising=False)

    assert indexer.index_chunks(_chunks()) == len(DOCS)
    assert c.count("idx").count == len(DOCS)

    # il vettore sparso scritto dall'indicizzatore trova il codice fiscale
    top = c.query_points("idx", query=query_vector("80057570584"), using=SPARSE_VECTOR, limit=1, with_payload=True).points[0]
    assert top.payload["source"] == "s1"
    # e il denso e' interrogabile per nome
    assert c.query_points("idx", query=[1.0, 0.0], using=DENSE_VECTOR, limit=1).points
    c.close()
    shutil.rmtree(path, ignore_errors=True)


def test_il_gestore_qdrant_crea_la_collection_nel_formato_ibrido(monkeypatch):
    from src.vectorstore import qdrant_client as modulo

    path = tempfile.mkdtemp()
    c = QdrantClient(path=path)
    manager = modulo.QdrantClientManager.__new__(modulo.QdrantClientManager)
    manager.client, manager.collection_name = c, "nuova"
    monkeypatch.setattr(
        modulo.ConfigLoader, "get_qdrant_config",
        classmethod(lambda cls: {"qdrant": {"vectors": {"size": 8, "distance": "Cosine"}}}),
    )
    manager._ensure_collection()

    info = c.get_collection("nuova").config.params
    assert info.vectors[DENSE_VECTOR].size == 8
    assert info.sparse_vectors[SPARSE_VECTOR].modifier == models.Modifier.IDF
    c.close()
    shutil.rmtree(path, ignore_errors=True)
