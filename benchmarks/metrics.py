#!/usr/bin/env python3
"""
Metriche di Information Retrieval per la valutazione del sistema RAG CNI.

Modulo unico e condiviso: sia l'harness di valutazione (`run_evaluation.py`)
sia l'API devono importare da qui, in modo che esista una sola definizione di
"documento rilevante" e le metriche non possano divergere fra loro.

--------------------------------------------------------------------------
DEFINIZIONE DI RILEVANZA
--------------------------------------------------------------------------
La verita' nota (ground truth) e' l'insieme `expected_sources` del golden
dataset: frammenti di URL che identificano i documenti che *contengono
davvero* la risposta.

Un chunk recuperato e' RILEVANTE se almeno uno di quei frammenti compare nel
suo campo `source` oppure nel suo `title`.

La stessa funzione (`doc_is_relevant`) e' usata da TUTTE le metriche. Questo
elimina l'asimmetria della versione precedente, in cui hit@k e MRR
accettavano una corrispondenza su source *o* title mentre il recall contava
solo quelle su source, gonfiando sistematicamente le prime due.

Nota metodologica importante: la rilevanza NON deve mai essere derivata dal
punteggio di similarita' del retriever. Usare `score > soglia` come verita'
significa usare il giudizio del sistema per valutare il sistema stesso: la
metrica risultante e' circolare e non misura nulla.

--------------------------------------------------------------------------
DEFINIZIONI DELLE METRICHE (tutte troncate a k)
--------------------------------------------------------------------------
  Hit@k        1 se almeno un documento rilevante compare nei primi k, 0
               altrimenti. Aggregato sulle domande diventa la frazione di
               domande "servite" entro k.

  Recall@k     |fonti attese distinte trovate nei primi k| / |fonti attese|
               Al denominatore il totale delle fonti attese, NON k.

  Precision@k  |documenti rilevanti nei primi k| / k
               Con ground truth a livello di fonte, il valore massimo
               raggiungibile dipende da quanti chunk di quella fonte
               esistono nell'indice: e' una metrica descrittiva, non un
               obiettivo da massimizzare. Riportarla con questa cautela.

  MRR          1 / (rank del primo documento rilevante), 0 se assente.
               Calcolato sull'intera lista fornita.

  nDCG@k       Discounted Cumulative Gain normalizzato, guadagni binari.
               Premia i documenti rilevanti in posizione alta in modo piu'
               graduale di Hit@k.

--------------------------------------------------------------------------
PRE- E POST-RERANKING
--------------------------------------------------------------------------
Le metriche vanno calcolate su entrambe le liste:

  retrieved_docs  ->  cosa produce il retriever denso
  context_docs    ->  cosa riceve davvero l'LLM, dopo il reranking

Il confronto fra le due e' il guadagno del reranker, misurato direttamente
(vedi `reranker_gain`).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

DEFAULT_K_VALUES: tuple[int, ...] = (1, 3, 5, 10)
MATCH_FIELDS: tuple[str, ...] = ("source", "title")


# ---------------------------------------------------------------------------
# Rilevanza
# ---------------------------------------------------------------------------

def _norm(value: Any) -> str:
    return (value or "").strip().lower()


def matched_sources(doc: dict[str, Any], expected_sources: Iterable[str]) -> set[str]:
    """Sottoinsieme di `expected_sources` soddisfatto da questo documento.

    Serve al Recall@k, che deve contare le *fonti attese distinte* trovate e
    non il numero di chunk recuperati (una singola pagina puo' generare
    decine di chunk, che altrimenti conterebbero come altrettante fonti).
    """
    haystack = " ".join(_norm(doc.get(field)) for field in MATCH_FIELDS)
    return {frag for frag in expected_sources if frag and _norm(frag) in haystack}


def doc_is_relevant(doc: dict[str, Any], expected_sources: Iterable[str]) -> bool:
    """Unica definizione di rilevanza usata da tutte le metriche."""
    return bool(matched_sources(doc, expected_sources))


def relevance_vector(docs: Sequence[dict[str, Any]], expected_sources: Iterable[str]) -> list[int]:
    expected = list(expected_sources)
    return [int(doc_is_relevant(d, expected)) for d in docs]


# ---------------------------------------------------------------------------
# Metriche elementari (su vettore di rilevanza gia' calcolato)
# ---------------------------------------------------------------------------

def hit_at_k(relevance: Sequence[int], k: int) -> int:
    return int(any(relevance[:k]))


def precision_at_k(relevance: Sequence[int], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(relevance[:k]) / k


def reciprocal_rank(relevance: Sequence[int]) -> float:
    for i, rel in enumerate(relevance):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


def first_relevant_rank(relevance: Sequence[int]) -> int | None:
    for i, rel in enumerate(relevance):
        if rel:
            return i + 1
    return None


def ndcg_at_k(relevance: Sequence[int], k: int) -> float:
    """nDCG@k con guadagni binari.

    DCG  = somma di rel_i / log2(i + 1) per i = 1..k
    IDCG = stesso calcolo sull'ordinamento ideale (tutti i rilevanti in testa)
    """
    cut = list(relevance[:k])
    if not cut:
        return 0.0
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(cut))
    n_ideal = min(sum(relevance), k)
    if n_ideal == 0:
        return 0.0
    idcg = sum(1 / math.log2(i + 2) for i in range(n_ideal))
    return dcg / idcg if idcg else 0.0


def recall_at_k(
    docs: Sequence[dict[str, Any]],
    expected_sources: Sequence[str],
    k: int,
) -> float:
    """Frazione di fonti attese distinte ritrovate entro i primi k documenti.

    Il troncamento a k e' il punto chiave: la versione precedente scorreva
    l'intera lista dei candidati (top_k = 25) producendo Recall = 1.00 su
    tutte le domande, un valore incoerente con Hit@10 = 0.7 nella stessa
    tabella.
    """
    if not expected_sources:
        return 0.0
    found: set[str] = set()
    for doc in docs[:k]:
        found |= matched_sources(doc, expected_sources)
    return len(found) / len(expected_sources)


# ---------------------------------------------------------------------------
# Valutazione di un singolo ranking
# ---------------------------------------------------------------------------

def evaluate_ranking(
    docs: Sequence[dict[str, Any]],
    expected_sources: Sequence[str],
    k_values: Sequence[int] = DEFAULT_K_VALUES,
) -> dict[str, Any]:
    """Tutte le metriche per una singola domanda su una singola lista ordinata.

    Restituisce anche `relevance`, il vettore binario posizione per posizione:
    e' la materia prima dell'analisi degli errori (a che rank esce la risposta
    giusta? chi la scarta?) e va conservato nel run.
    """
    expected = [s for s in expected_sources if s]
    rel = relevance_vector(docs, expected)
    rank = first_relevant_rank(rel)

    out: dict[str, Any] = {
        "n_docs": len(docs),
        "n_expected_sources": len(expected),
        "first_relevant_rank": rank,
        "mrr": reciprocal_rank(rel),
        "relevance": rel,
    }
    for k in k_values:
        out[f"hit_at_{k}"] = hit_at_k(rel, k)
        out[f"precision_at_{k}"] = round(precision_at_k(rel, k), 4)
        out[f"recall_at_{k}"] = round(recall_at_k(docs, expected, k), 4)
        out[f"ndcg_at_{k}"] = round(ndcg_at_k(rel, k), 4)
    return out


def evaluate_stages(
    retrieved_docs: Sequence[dict[str, Any]],
    context_docs: Sequence[dict[str, Any]],
    expected_sources: Sequence[str],
    k_values: Sequence[int] = DEFAULT_K_VALUES,
) -> dict[str, Any]:
    """Metriche su entrambi gli stadi della pipeline.

    `retrieved` misura il retriever denso; `context` misura cio' che l'LLM
    riceve davvero dopo il reranking. Valutare solo il primo, come faceva la
    versione precedente, significa non misurare la pipeline reale e perdere
    il guadagno del reranker.
    """
    return {
        "retrieved": evaluate_ranking(retrieved_docs, expected_sources, k_values),
        "context": evaluate_ranking(context_docs, expected_sources, k_values),
    }


def reranker_gain(stages: dict[str, Any], k: int = 5) -> dict[str, Any]:
    """Differenza post-rerank meno pre-rerank, per una singola domanda.

    Aggregata sulle domande con un test appaiato (vedi `stats.paired_report`)
    diventa l'ablation study del reranker.
    """
    pre, post = stages["retrieved"], stages["context"]
    return {
        "d_mrr": round(post["mrr"] - pre["mrr"], 4),
        f"d_hit_at_{k}": post.get(f"hit_at_{k}", 0) - pre.get(f"hit_at_{k}", 0),
        f"d_recall_at_{k}": round(post.get(f"recall_at_{k}", 0.0) - pre.get(f"recall_at_{k}", 0.0), 4),
        f"d_ndcg_at_{k}": round(post.get(f"ndcg_at_{k}", 0.0) - pre.get(f"ndcg_at_{k}", 0.0), 4),
        "rank_pre": pre["first_relevant_rank"],
        "rank_post": post["first_relevant_rank"],
    }


# ---------------------------------------------------------------------------
# Aggregazione su piu' domande
# ---------------------------------------------------------------------------

def aggregate_rankings(
    per_question: Sequence[dict[str, Any]],
    k_values: Sequence[int] = DEFAULT_K_VALUES,
) -> dict[str, float]:
    """Media semplice di ciascuna metrica sulle domande.

    Gli intervalli di confidenza NON si calcolano qui: servono i valori
    grezzi per domanda. Usare `stats.summarize_metric` sulle liste
    corrispondenti.
    """
    n = len(per_question)
    if n == 0:
        return {}

    keys = ["mrr"]
    for k in k_values:
        keys += [f"hit_at_{k}", f"precision_at_{k}", f"recall_at_{k}", f"ndcg_at_{k}"]

    return {key: round(sum(q.get(key, 0) or 0 for q in per_question) / n, 4) for key in keys}


def column(per_question: Sequence[dict[str, Any]], key: str) -> list[float]:
    """Estrae i valori grezzi di una metrica, per i test statistici."""
    return [float(q.get(key, 0) or 0) for q in per_question]
