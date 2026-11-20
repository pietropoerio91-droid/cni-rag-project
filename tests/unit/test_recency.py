import sys
import types

from src.rag.prompt_builder import PromptBuilder
from src.rag.recency import apply_recency


def _docs():
    # Caso Q01: due comunicati sul presidente con pertinenza simile e una pagina meno pertinente.
    return [
        {"content": "Zambrano al timone del CNI fino al 2021", "rerank_score": 5.0, "date": "2016-07-01"},
        {"content": "Eletti i nuovi vertici del CNI", "rerank_score": 4.8, "date": "2022-07-01"},
        {"content": "Pagina non pertinente", "rerank_score": -3.0, "date": "2026-11-16"},
    ]


def test_con_peso_zero_l_ordine_non_cambia():
    docs = _docs()
    assert apply_recency(docs, 0.0) is docs
    assert [d["rerank_score"] for d in apply_recency(_docs(), 0.0)] == [5.0, 4.8, -3.0]


def test_tra_documenti_di_pertinenza_simile_vince_il_piu_recente():
    out = apply_recency(_docs(), 0.2)
    assert out[0]["content"] == "Eletti i nuovi vertici del CNI"


def test_un_documento_recente_ma_non_pertinente_non_sale_in_cima():
    out = apply_recency(_docs(), 0.2)
    assert out[-1]["content"] == "Pagina non pertinente"


def test_documenti_senza_data_hanno_recenza_neutra():
    docs = [{"rerank_score": 1.0, "date": ""}, {"rerank_score": 1.0, "date": "2020-01-01"},
            {"rerank_score": 1.0, "date": "2024-01-01"}]
    out = {d["date"]: d["recency"] for d in apply_recency(docs, 0.5)}
    assert out == {"": 0.5, "2020-01-01": 0.0, "2024-01-01": 1.0}


def test_stessa_data_per_tutti_conta_solo_la_pertinenza():
    docs = [{"rerank_score": 1.0, "date": "2022-01-01"}, {"rerank_score": 2.0, "date": "2022-01-01"}]
    assert [d["rerank_score"] for d in apply_recency(docs, 0.3)] == [2.0, 1.0]


def test_prompt_senza_date_identico_a_quello_della_tesi():
    docs = [{"source": "u", "title": "T", "content": "c"}]
    testo = PromptBuilder.build_stream_prompt("q", docs)
    assert "DATE DEI DOCUMENTI" not in testo
    assert "[Posizione 1 - T]\nFonte: u" in testo


def test_prompt_con_date_mostra_la_data_e_la_regola():
    docs = [{"source": "u", "title": "T", "content": "c", "date": "2022-07-01", "date_precision": "year"},
            {"source": "v", "title": "S", "content": "d", "date": "2026-11-16", "date_precision": "day"}]
    testo = PromptBuilder.build_prompt("q", docs)[0]["content"]
    assert "DATE DEI DOCUMENTI" in testo
    assert "[Posizione 1 - T - data: 2022]" in testo
    assert "[Posizione 2 - S - data: 16/11/2026]" in testo
    assert PromptBuilder.format_date("2023-01-15", "month") == "gennaio 2023"


def _reranker(monkeypatch, weight):
    from src.rag import reranker as modulo

    monkeypatch.setattr(
        modulo.ConfigLoader, "get_rag_config",
        classmethod(lambda cls: {"reranking": {"enabled": True, "top_k": 2, "model": "finto",
                                               "recency_weight": weight}}),
    )

    class CrossEncoderFinto:
        def __init__(self, name):
            pass

        def predict(self, pairs):
            return [{"vecchio": 5.0, "nuovo": 4.8, "altro": -3.0}[testo] for _, testo in pairs]

    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        types.SimpleNamespace(CrossEncoder=CrossEncoderFinto))
    return modulo.Reranker()


def _candidati():
    return [{"content": "vecchio", "date": "2016-07-01"}, {"content": "nuovo", "date": "2022-07-01"},
            {"content": "altro", "date": ""}]


def test_reranker_senza_peso_alla_recenza_come_prima(monkeypatch):
    out = _reranker(monkeypatch, 0.0).rerank("q", _candidati())
    assert [d["content"] for d in out] == ["vecchio", "nuovo"]


def test_reranker_con_peso_alla_recenza(monkeypatch):
    out = _reranker(monkeypatch, 0.2).rerank("q", _candidati())
    assert [d["content"] for d in out] == ["nuovo", "vecchio"]
    assert "final_score" in out[0]
