import pytest

from src.rag import reranker as modulo

DOCS = [{"content": "a", "score": 0.2}, {"content": "b", "score": 0.9}, {"content": "c", "score": 0.5}]


def _reranker(monkeypatch, allow_fallback):
    monkeypatch.setattr(
        modulo.ConfigLoader, "get_rag_config",
        classmethod(lambda cls: {"reranking": {"enabled": True, "top_k": 2, "model": "modello-inesistente",
                                               "allow_fallback": allow_fallback}}),
    )
    import sentence_transformers

    def _fail(name):
        raise OSError("rete assente")

    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _fail)
    return modulo.Reranker()


def test_se_il_modello_non_si_carica_il_sistema_si_ferma(monkeypatch):
    with pytest.raises(RuntimeError, match="allow_fallback"):
        _reranker(monkeypatch, allow_fallback=False).rerank("q", list(DOCS))


def test_con_consenso_esplicito_si_prosegue_ordinando_per_punteggio(monkeypatch):
    out = _reranker(monkeypatch, allow_fallback=True).rerank("q", list(DOCS))
    assert [d["content"] for d in out] == ["b", "c"]


def test_senza_risultati_non_carica_nulla(monkeypatch):
    assert _reranker(monkeypatch, allow_fallback=False).rerank("q", []) == []
