import pytest
"""Verifiche sull'indice lessicale e sulla fusione dei ranghi.

Non richiedono Qdrant ne' modelli: lavorano su documenti costruiti a mano.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.rag.fusion import reciprocal_rank_fusion
from src.rag.sparse_index import BM25Index, tokenizza


def doc(source, content, title="", chunk_index=0):
    return {"content": content, "source": source, "title": title,
            "chunk_index": chunk_index, "category": ""}


def test_tokenizza_conserva_le_cifre():
    assert "80057570584" in tokenizza("Codice fiscale: 80057570584")


def test_tokenizza_ripiega_i_diacritici():
    assert tokenizza("Università") == tokenizza("universita")


def test_tokenizza_scarta_i_token_di_un_carattere():
    assert tokenizza("a b co") == ["co"]


def test_un_termine_raro_porta_in_testa_il_documento_giusto():
    """Il caso Q12: un codice fiscale compare in una pagina sola e deve vincere."""
    documenti = [
        doc("/urp", "Il codice fiscale del CNI e' 80057570584 e la sede e' a Roma."),
        doc("/cni", "Il Consiglio Nazionale degli Ingegneri e' un ente di diritto pubblico."),
        doc("/servizi", "Servizi e convenzioni per gli iscritti agli ordini provinciali."),
    ]
    indice = BM25Index(documenti)
    risultati = indice.retrieve("Qual e' il codice fiscale del CNI?", top_k=3)
    assert risultati[0]["source"] == "/urp"


def test_il_titolo_e_cercabile():
    """Molte pagine di approdo hanno il tema nel titolo e link nel corpo."""
    documenti = [
        doc("/whistleblowing", "Informativa privacy. Clicca qui per segnalare.", title="Whistleblowing"),
        doc("/altro", "Pagina di servizio senza attinenza."),
    ]
    indice = BM25Index(documenti, include_title=True)
    assert indice.retrieve("whistleblowing", top_k=2)[0]["source"] == "/whistleblowing"

    senza = BM25Index(documenti, include_title=False)
    assert senza.retrieve("whistleblowing", top_k=2) == []


def test_query_senza_termini_noti_non_restituisce_nulla():
    indice = BM25Index([doc("/a", "testo qualsiasi")])
    assert indice.retrieve("zzzz qqqq", top_k=5) == []


def test_la_fusione_premia_chi_compare_in_entrambe_le_liste():
    a = doc("/a", "", chunk_index=0)
    b = doc("/b", "", chunk_index=0)
    c = doc("/c", "", chunk_index=0)
    denso = [a, b]        # /a primo, /b secondo
    lessicale = [c, a]    # /c primo, /a secondo
    fusa = reciprocal_rank_fusion([denso, lessicale], k=60)
    assert fusa[0]["source"] == "/a"          # presente in entrambe
    assert {d["source"] for d in fusa} == {"/a", "/b", "/c"}


def test_la_fusione_deduplica_per_chunk_e_taglia_a_top_k():
    a0 = doc("/a", "", chunk_index=0)
    a1 = doc("/a", "", chunk_index=1)
    fusa = reciprocal_rank_fusion([[a0, a1], [a0]], k=60, top_k=1)
    assert len(fusa) == 1
    assert (fusa[0]["source"], fusa[0]["chunk_index"]) == ("/a", 0)


def test_la_fusione_conserva_i_punteggi_dei_canali():
    d = dict(doc("/a", ""), score=0.61)
    l = dict(doc("/a", ""), score=12.4)
    fusa = reciprocal_rank_fusion([[d], [l]], k=60)
    assert fusa[0]["score_denso"] == 0.61
    assert fusa[0]["score_lessicale"] == 12.4


# --------------------------------------------------------------------------- #
# Flusso di HybridRetriever, verificato senza Qdrant ne' modelli di embedding.
# L'oggetto viene costruito con __new__ e popolato a mano: si esercita solo la
# logica di retrieve(), che e' quella che ci interessa.
# --------------------------------------------------------------------------- #

class _RetrieverDensoFinto:
    def __init__(self, risultati):
        self.risultati = risultati
        self.ultimo_top_k = None

    def retrieve(self, query, top_k=None, filter_condition=None):
        self.ultimo_top_k = top_k
        return self.risultati[:top_k] if top_k else self.risultati


def _costruisci_ibrido(enabled, densi, lessicali, top_k=25):
    # Importato qui dentro: HybridRetriever tira dentro langchain e qdrant, che
    # non servono a questo test ma devono essere installati per importarlo.
    from src.rag.hybrid_retriever import HybridRetriever
    r = HybridRetriever.__new__(HybridRetriever)
    r.vector_retriever = _RetrieverDensoFinto(densi)
    r.query_classifier = type("C", (), {"classify": staticmethod(lambda q: "generico")})()
    r.top_k = top_k
    r.hybrid_config = {}
    r.hybrid_enabled = enabled
    r.backend = "memoria"
    r.dense_top_k = 50
    r.sparse_top_k = 50
    r.rrf_k = 60
    r.category_filter = False
    r._indice_lessicale = BM25Index(lessicali) if lessicali else BM25Index([])
    return r


def test_con_bandiera_spenta_il_comportamento_e_quello_della_linea_di_base():
    densi = [doc(f"/d{i}", "contenuto", chunk_index=i) for i in range(30)]
    r = _costruisci_ibrido(False, densi, [], top_k=25)
    out = r.retrieve("una domanda")
    assert len(out) == 25
    assert r.vector_retriever.ultimo_top_k == 25      # chiede esattamente top_k
    assert [d["source"] for d in out] == [f"/d{i}" for i in range(25)]


def test_con_bandiera_accesa_il_canale_lessicale_porta_dentro_cio_che_il_denso_manca():
    """Il caso Q12: il denso non trova mai la pagina del codice fiscale."""
    densi = [doc(f"/rumore{i}", "testo generico sul consiglio", chunk_index=i) for i in range(30)]
    corpus = densi + [doc("/urp", "Il codice fiscale del CNI e' 80057570584.", chunk_index=0)]
    r = _costruisci_ibrido(True, densi, corpus, top_k=25)
    out = r.retrieve("Qual e' il codice fiscale del CNI?")
    assert "/urp" in [d["source"] for d in out]
    assert r.vector_retriever.ultimo_top_k == 50      # pescata larga prima della fusione
    assert len(out) == 25                              # budget del riordino invariato


def test_un_backend_sconosciuto_viene_rifiutato(monkeypatch):
    from src.rag import hybrid_retriever as modulo
    monkeypatch.setattr(
        modulo.ConfigLoader, "get_rag_config",
        classmethod(lambda cls: {"retrieval": {"hybrid_search": {"backend": "elasticsearch"}}}),
    )
    with pytest.raises(ValueError, match="backend"):
        modulo.HybridRetriever(embedding_model=None)
