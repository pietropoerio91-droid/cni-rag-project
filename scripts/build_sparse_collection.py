#!/usr/bin/env python3
"""Costruisce una collection con vettore denso e vettore sparso BM25.

Copia da una collection esistente i vettori densi (senza rifare gli embedding) e
i payload, e aggiunge per ogni chunk il vettore sparso BM25 calcolato da
`src/vectorstore/bm25_sparse.py`. La collection di partenza non viene modificata.

Serve una collection nuova perche' Qdrant non permette di aggiungere un vettore
con nome a una collection il cui unico vettore e' anonimo.

Usage:
    python scripts/build_sparse_collection.py \
        --source cni_documents_multiling --target cni_documents_multiling_bm25

Da lanciare con l'API ferma: Qdrant in modalita' locale prende un lock esclusivo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import models

from src.core.config_loader import ConfigLoader
from src.vectorstore.bm25_sparse import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    average_length,
    collection_schema,
    document_vector,
    indexed_text,
    term_index,
    tokenize,
)
from src.vectorstore.qdrant_client import QdrantClientManager


def read_source(client, source: str, batch: int = 500) -> list:
    points, offset = [], None
    while True:
        chunk, offset = client.scroll(
            collection_name=source, limit=batch, offset=offset, with_payload=True, with_vectors=True
        )
        points.extend(chunk)
        if offset is None:
            return points


def main() -> None:
    bm25 = ConfigLoader.get_rag_config().get("retrieval", {}).get("hybrid_search", {}).get("bm25", {})
    ap = argparse.ArgumentParser(description="Collection con vettore denso e sparso BM25")
    ap.add_argument("--source", required=True, help="collection da cui copiare vettori e payload")
    ap.add_argument("--target", required=True, help="collection da creare")
    ap.add_argument("--k1", type=float, default=bm25.get("k1", 1.2), help="default: rag_config.yaml")
    ap.add_argument("--b", type=float, default=bm25.get("b", 0.75), help="default: rag_config.yaml")
    ap.add_argument("--no-title", action="store_true",
                    help="non includere il titolo nel testo indicizzato (default: rag_config.yaml)")
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()

    client = QdrantClientManager().get_client()
    existing = {c.name for c in client.get_collections().collections}
    if args.source not in existing:
        sys.exit(f"collection di partenza '{args.source}' non trovata")
    if args.target in existing:
        sys.exit(f"'{args.target}' esiste gia': non la sovrascrivo")

    points = read_source(client, args.source)
    print(f"{len(points)} chunk letti da '{args.source}'")

    include_title = bm25.get("include_title", True) and not args.no_title
    tokens = [tokenize(indexed_text(p.payload or {}, include_title)) for p in points]
    avgdl = average_length(tokens)

    vocabulary = {t for tk in tokens for t in tk}
    collisions = len(vocabulary) - len({term_index(t) for t in vocabulary})
    print(f"lunghezza media {avgdl:.1f} token · {len(vocabulary)} termini distinti · "
          f"{collisions} collisioni di indice")

    dim = len(points[0].vector)
    client.create_collection(
        collection_name=args.target,
        **collection_schema(dim),
        metadata={"bm25": {"k1": args.k1, "b": args.b, "avgdl": avgdl,
                           "include_title": include_title, "source": args.source}},
    )

    for i in range(0, len(points), args.batch):
        client.upsert(
            collection_name=args.target,
            points=[
                models.PointStruct(
                    id=p.id,
                    vector={DENSE_VECTOR: p.vector, SPARSE_VECTOR: document_vector(tk, avgdl, args.k1, args.b)},
                    payload=p.payload,
                )
                for p, tk in zip(points[i:i + args.batch], tokens[i:i + args.batch])
            ],
        )
    print(f"'{args.target}': {client.count(args.target).count} punti (attesi {len(points)})")


if __name__ == "__main__":
    main()
