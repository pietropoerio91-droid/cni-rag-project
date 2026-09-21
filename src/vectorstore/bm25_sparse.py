"""Vettori sparsi BM25 per Qdrant.

Perche' cosi'
-------------
Qdrant sa fare il prodotto scalare fra vettori sparsi e, con il modificatore
`IDF`, moltiplica da se' il peso di ogni termine per la sua IDF calcolata sulla
collection. Basta quindi memorizzare per ogni chunk la parte di BM25 che non
dipende dal resto del corpus:

    peso(t, d) = tf(t,d) * (k1 + 1) / (tf(t,d) + k1 * (1 - b + b * |d| / avgdl))

e interrogare con un vettore che vale `1` per ogni termine della domanda. Il
punteggio restituito e' il BM25 con IDF alla Lucene
(`ln(1 + (N - df + 0.5) / (df + 0.5))`, formulazione di Robertson e Zaragoza).

Il tokenizzatore usa minuscole, diacritici ripiegati e cifre conservate
(`80057570584` deve restare cercabile). Non ha stopword ne' stemming: le parole
comuni pesano poco per effetto dell'IDF, ma "ingegnere" e "ingegneri" restano
termini distinti.

Limite da conoscere: `avgdl` entra nei pesi dei documenti, quindi se il corpus
cambia la collection va ricostruita.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

from qdrant_client import models

_TOKEN = re.compile(r"[a-z0-9]+")

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"


def tokenize(text: str) -> list[str]:
    """Minuscole, diacritici rimossi, token alfanumerici di almeno due caratteri.

    I diacritici vengono ripiegati perche' le domande sono scritte indifferentemente
    con o senza accento (`universita` / `universita'`).
    """
    if not text:
        return []
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return [t for t in _TOKEN.findall(flat) if len(t) >= 2]


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


def average_length(token_lists: Iterable[list[str]]) -> float:
    lengths = [len(t) for t in token_lists]
    return sum(lengths) / len(lengths) if lengths else 0.0


def collection_schema(dense_size: int, distance: models.Distance = models.Distance.COSINE, on_disk: bool = False) -> dict:
    """Argomenti di `create_collection` per una collection con vettore denso e sparso.

    E' l'unica definizione dello schema: la usano sia il gestore Qdrant sia lo
    script di costruzione, cosi' la collection ha lo stesso formato ovunque venga
    creata. Il modificatore IDF fa calcolare a Qdrant l'IDF sull'intera collection.
    """
    return {
        "vectors_config": {DENSE_VECTOR: models.VectorParams(size=dense_size, distance=distance, on_disk=on_disk)},
        "sparse_vectors_config": {SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    }


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
