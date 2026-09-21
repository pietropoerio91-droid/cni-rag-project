"""Vettori sparsi BM25 per Qdrant.

Perche' cosi'
-------------
Qdrant sa fare il prodotto scalare fra vettori sparsi e, con il modificatore
`IDF`, moltiplica da se' il peso di ogni termine per la sua IDF calcolata sulla
collection. Basta quindi memorizzare per ogni chunk la parte di BM25 che non
dipende dal resto del corpus:

    peso(t, d) = tf(t,d) * (k1 + 1) / (tf(t,d) + k1 * (1 - b + b * |d| / avgdl))

e interrogare con un vettore che vale `1` per ogni termine della domanda. Il
punteggio restituito e' lo stesso del BM25 con IDF alla Lucene
(`ln(1 + (N - df + 0.5) / (df + 0.5))`), verificato contro l'implementazione in
memoria di `src/rag/sparse_index.py`.

Il tokenizzatore e' lo stesso del BM25 in memoria: minuscole, diacritici
ripiegati, cifre conservate (`80057570584` deve restare cercabile).

Limite da conoscere: `avgdl` entra nei pesi dei documenti, quindi se il corpus
cambia la collection va ricostruita.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable

from qdrant_client import models

from src.rag.sparse_index import tokenizza as tokenize

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"


def term_index(term: str) -> int:
    """Indice u32 stabile di un termine.

    Un hash evita di dover salvare e mantenere un vocabolario; le collisioni sono
    rare (con ~60.000 termini distinti se ne attende meno di una) e chi costruisce
    la collection le conta e le riporta.
    """
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=4).digest(), "big")


def indexed_text(payload: dict[str, Any], include_title: bool = True) -> str:
    """Il testo su cui si calcola il BM25: titolo e contenuto, come nell'indice in memoria."""
    text = payload.get("content", "") or ""
    title = payload.get("title", "")
    if include_title and title:
        text = f"{title}\n{text}"
    return text


def _sparse(weights: dict[int, float]) -> models.SparseVector:
    """Un indice puo' comparire una volta sola: in caso di collisione i pesi si sommano."""
    indices = sorted(weights)
    return models.SparseVector(indices=indices, values=[weights[i] for i in indices])


def document_vector(tokens: Iterable[str], avgdl: float, k1: float = 1.2, b: float = 0.75) -> models.SparseVector:
    tokens = list(tokens)
    norm = 1.0 - b + b * (len(tokens) / avgdl if avgdl else 0.0)
    weights: dict[int, float] = {}
    for term, tf in Counter(tokens).items():
        i = term_index(term)
        weights[i] = weights.get(i, 0.0) + tf * (k1 + 1.0) / (tf + k1 * norm)
    return _sparse(weights)


def query_vector(query: str) -> models.SparseVector:
    """Peso pari alla frequenza del termine nella domanda: come nel BM25 in memoria."""
    weights: dict[int, float] = {}
    for term, count in Counter(tokenize(query)).items():
        i = term_index(term)
        weights[i] = weights.get(i, 0.0) + float(count)
    return _sparse(weights)
