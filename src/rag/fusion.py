"""Fusione di piu' liste di candidati provenienti da canali di recupero diversi.

Perche' la fusione dei ranghi e non la somma pesata
---------------------------------------------------
I due canali producono punteggi su scale incomparabili: la similarita' coseno
vive in [-1, 1] ed e' soggetta a una soglia, BM25 non e' limitato e dipende
dalla rarita' dei termini e dalla dimensione del corpus. Sommarli richiede una
normalizzazione arbitraria e due pesi da calibrare, che andrebbero poi
giustificati.

La Reciprocal Rank Fusion ignora i punteggi e considera solo la **posizione** di
ciascun documento in ciascuna lista:

    RRF(d) = somma sulle liste di 1 / (k + rango(d))

La costante k attenua il vantaggio delle primissime posizioni; il valore
convenzionale e' 60. Il risultato non dipende dalle scale e non ha pesi da
tarare.

Limite da tenere presente: la fusione puo' solo riordinare cio' che almeno uno
dei due canali ha trovato. Non fa comparire documenti che entrambi hanno mancato.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)


def chiave_chunk(doc: dict[str, Any]) -> tuple[str, Any]:
    """Identita' di un chunk: la pagina d'origine piu' la sua posizione nella pagina."""
    return (doc.get("source", ""), doc.get("chunk_index", 0))


def reciprocal_rank_fusion(
    liste: Sequence[Iterable[dict[str, Any]]],
    k: int = 60,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Fonde piu' liste ordinate in una sola, per reciproco del rango.

    Ogni documento conserva i punteggi originali dei canali in cui compare,
    sotto le chiavi `score_denso` e `score_lessicale` quando disponibili, cosi'
    che restino ispezionabili nei risultati della valutazione.
    """
    punteggi: dict[tuple[str, Any], float] = {}
    rappresentante: dict[tuple[str, Any], dict[str, Any]] = {}
    origini: dict[tuple[str, Any], dict[str, float]] = {}

    etichette = ["denso", "lessicale"]

    for indice_lista, lista in enumerate(liste):
        etichetta = etichette[indice_lista] if indice_lista < len(etichette) else f"canale{indice_lista}"
        for rango, doc in enumerate(lista, start=1):
            chiave = chiave_chunk(doc)
            punteggi[chiave] = punteggi.get(chiave, 0.0) + 1.0 / (k + rango)
            origini.setdefault(chiave, {})[etichetta] = doc.get("score", 0.0)
            # Il primo canale che propone un chunk ne fornisce la copia di lavoro.
            rappresentante.setdefault(chiave, dict(doc))

    ordinati = sorted(punteggi.items(), key=lambda kv: kv[1], reverse=True)
    if top_k is not None:
        ordinati = ordinati[:top_k]

    risultati: list[dict[str, Any]] = []
    for chiave, punteggio in ordinati:
        doc = rappresentante[chiave]
        for etichetta, valore in origini.get(chiave, {}).items():
            doc[f"score_{etichetta}"] = valore
        doc["score"] = punteggio
        risultati.append(doc)
    return risultati
