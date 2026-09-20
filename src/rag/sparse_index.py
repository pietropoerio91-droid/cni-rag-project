"""Indice lessicale BM25 sui chunk gia' presenti in Qdrant.

Perche' esiste
--------------
Il recupero denso rappresenta il significato, non le parole. Un codice fiscale,
un cognome o una sigla non hanno un intorno semantico: qualunque modello di
embedding, con qualunque finestra, non puo' rappresentarli in modo distintivo.
La misura sul golden dataset mostra che in 13 domande fallite su 14 la fonte
attesa non entra nemmeno fra i 25 candidati densi, e che il termine richiesto e'
quasi sempre un token lessicale (`Perrini`, `WFEO`, `80057570584`, `Trento`).

BM25 e' il complemento naturale: cerca le parole esatte e pesa i termini rari.

Perche' in memoria e non su un motore di ricerca
------------------------------------------------
Normalmente BM25 vive in un indice invertito persistente (Lucene, Elasticsearch,
Solr). Su 13.784 chunk l'indice invertito in memoria si costruisce in pochi
secondi e risponde in millisecondi: e' la scelta proporzionata alla scala di
questo lavoro. Il testo integrale dei chunk e' gia' nel payload di Qdrant,
quindi non serve ne' un nuovo crawling ne' una reindicizzazione.

Formulazione
------------
BM25 nella forma di Robertson e Zaragoza, con la variante di IDF sempre positiva
usata da Lucene:

    idf(t)   = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
    score(d) = somma su t in query di
               idf(t) * tf(t,d) * (k1 + 1) /
               (tf(t,d) + k1 * (1 - b + b * |d| / avgdl))

I valori predefiniti k1 = 1,2 e b = 0,75 sono quelli convenzionali.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenizza(testo: str) -> list[str]:
    """Minuscole, diacritici rimossi, token alfanumerici di almeno due caratteri.

    I diacritici vengono ripiegati perche' le domande degli utenti sono scritte
    indifferentemente con o senza accento (`universita` / `universita'`). Le
    cifre sono conservate: `80057570584` deve restare un token cercabile.
    """
    if not testo:
        return []
    piatto = unicodedata.normalize("NFKD", testo.lower())
    piatto = "".join(c for c in piatto if not unicodedata.combining(c))
    return [t for t in _TOKEN.findall(piatto) if len(t) >= 2]


class BM25Index:
    """Indice invertito con punteggio BM25.

    I documenti sono i chunk, nella stessa forma restituita da
    `VectorRetriever.retrieve`: dizionari con `content`, `source`, `title`,
    `chunk_index`, `category`.
    """

    def __init__(
        self,
        documenti: Iterable[dict[str, Any]],
        k1: float = 1.2,
        b: float = 0.75,
        include_title: bool = True,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.include_title = include_title

        self.documenti: list[dict[str, Any]] = list(documenti)
        self.n = len(self.documenti)

        # term -> {indice documento: frequenza}
        self.postings: dict[str, dict[int, int]] = defaultdict(dict)
        self.lunghezze: list[int] = [0] * self.n

        for i, doc in enumerate(self.documenti):
            testo = doc.get("content", "")
            if self.include_title and doc.get("title"):
                # Il titolo e' informativo su questo corpus: molte pagine di
                # approdo del portale hanno un titolo che nomina il tema mentre
                # il corpo e' un elenco di collegamenti.
                testo = f"{doc['title']}\n{testo}"
            token = tokenizza(testo)
            self.lunghezze[i] = len(token)
            for t in token:
                self.postings[t][i] = self.postings[t].get(i, 0) + 1

        totale = sum(self.lunghezze)
        self.avgdl = (totale / self.n) if self.n else 0.0

        self.idf: dict[str, float] = {}
        for t, posting in self.postings.items():
            df = len(posting)
            self.idf[t] = math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

        logger.info(
            f"Indice BM25 costruito: {self.n} documenti, {len(self.postings)} termini distinti, "
            f"lunghezza media {self.avgdl:.1f} token"
        )

    def punteggi(self, query: str) -> dict[int, float]:
        """Punteggio BM25 dei soli documenti che contengono almeno un termine."""
        accumulo: dict[int, float] = defaultdict(float)
        for t in tokenizza(query):
            posting = self.postings.get(t)
            if not posting:
                continue
            idf = self.idf[t]
            for i, tf in posting.items():
                norma = 1.0 - self.b + self.b * (self.lunghezze[i] / self.avgdl if self.avgdl else 0.0)
                accumulo[i] += idf * tf * (self.k1 + 1.0) / (tf + self.k1 * norma)
        return accumulo

    def retrieve(self, query: str, top_k: int = 50) -> list[dict[str, Any]]:
        """I `top_k` chunk con punteggio BM25 piu' alto, nella forma del retriever denso."""
        accumulo = self.punteggi(query)
        if not accumulo:
            return []
        migliori = sorted(accumulo.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        risultati: list[dict[str, Any]] = []
        for i, punteggio in migliori:
            doc = dict(self.documenti[i])
            doc["score"] = punteggio
            risultati.append(doc)
        return risultati


def carica_da_qdrant(client: Any, collection_name: str, batch: int = 1000) -> list[dict[str, Any]]:
    """Legge tutti i payload della collection, per costruirci sopra l'indice BM25.

    Non tocca i vettori: servono solo i testi, che l'indicizzazione ha gia'
    salvato accanto a essi.
    """
    documenti: list[dict[str, Any]] = []
    offset = None
    while True:
        punti, offset = client.scroll(
            collection_name=collection_name,
            limit=batch,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in punti:
            payload = p.payload or {}
            documenti.append({
                "content": payload.get("content", ""),
                "source": payload.get("source", ""),
                "title": payload.get("title", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "category": payload.get("category", ""),
            })
        if offset is None:
            break
    logger.info(f"Caricati {len(documenti)} chunk da '{collection_name}' per l'indice lessicale")
    return documenti
