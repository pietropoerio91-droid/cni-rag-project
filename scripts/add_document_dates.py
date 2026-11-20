#!/usr/bin/env python3
"""Aggiunge la data dei documenti a una collection esistente, senza rifare gli embedding.

La data di ogni documento e' prima di tutto quella di pubblicazione letta dalla
ricerca di cni.it (mappa di `scripts/fetch_site_dates.py`); per gli altri si
ricava dai file salvati dal crawler (JSON, HTML e PDF originali in `data/raw`)
con `src/ingestion/date_extractor.py`, e per le fonti senza JSON dal solo URL. La collection di partenza NON viene modificata: si
crea una copia con gli stessi vettori (denso e BM25) e la data nel payload di
ogni chunk (`date`, `date_source`, `date_precision`).

Senza `--target` lo script non scrive nulla e stampa solo la copertura: quanti
documenti e chunk hanno una data e da quale fonte. Serve a verificare
l'estrazione prima di creare la collection.

Usage:
    # 0. mappa delle date dalla ricerca del sito (circa 3 minuti, serve la rete)
    python scripts/fetch_site_dates.py

    # 1. anteprima (nessuna scrittura)
    python scripts/add_document_dates.py --source cni_documents_e5_bm25

    # 2. copia con le date
    python scripts/add_document_dates.py --source cni_documents_e5_bm25 --target cni_documents_e5_bm25_date

Poi si attiva la nuova collection (menu impostazioni o PUT /collections/active) e
si imposta `reranking.recency_weight` in config/rag_config.yaml.

Da lanciare con l'API ferma: Qdrant in modalita' locale prende un lock esclusivo.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import models

from src.ingestion.date_extractor import extract_document_date, load_document_dates
from src.ingestion.site_dates import load_site_dates, site_dates_settings
from src.vectorstore.bm25_sparse import DENSE_VECTOR, collection_schema
from src.vectorstore.qdrant_client import QdrantClientManager

DATE_KEYS = ("date", "date_source", "date_precision")


def read_points(client, collection: str, with_vectors: bool, batch: int = 500) -> list:
    points, offset = [], None
    while True:
        chunk, offset = client.scroll(
            collection_name=collection, limit=batch, offset=offset,
            with_payload=True, with_vectors=with_vectors,
        )
        points.extend(chunk)
        if offset is None:
            return points


def dates_for_sources(sources: set[str], raw_dir: Path,
                      site_dates: dict[str, dict] | None = None) -> tuple[dict[str, dict], int]:
    from_files = load_document_dates(raw_dir, site_dates=site_dates) if raw_dir.is_dir() else {}
    dates, url_only = {}, 0
    for src in sources:
        if src in from_files:
            dates[src] = from_files[src]
        else:
            url_only += 1
            dates[src] = extract_document_date({"url": src, "content": "", "meta": {"source": src}},
                                               site_dates=site_dates)
    return dates, url_only


def report(points: list, dates: dict[str, dict], url_only: int) -> None:
    sources = Counter((p.payload or {}).get("source", "") for p in points)
    documents_with = sum(1 for s in sources if dates.get(s))
    chunks_with = sum(n for s, n in sources.items() if dates.get(s))
    print(f"documenti: {len(sources)} · con data: {documents_with} ({documents_with / max(len(sources), 1):.1%})")
    print(f"chunk:     {len(points)} · con data: {chunks_with} ({chunks_with / max(len(points), 1):.1%})")
    if url_only:
        print(f"  ({url_only} fonti senza JSON in data/raw: data ricavata solo dall'URL)")

    by_source = Counter(d.get("date_source", "nessuna") for s, d in dates.items() if s in sources)
    print("\nfonte della data (documenti):")
    for name, n in by_source.most_common():
        print(f"  {n:6d}  {name}")

    years = Counter(d["date"][:4] for d in dates.values() if d)
    if years:
        print("\nanni:", " ".join(f"{y}:{n}" for y, n in sorted(years.items())))

    undated = [s for s in sources if not dates.get(s)]
    if undated:
        print("\nesempi senza data:")
        for s in sorted(undated)[:10]:
            print("  ", s)


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggiunge la data dei documenti a una copia della collection")
    ap.add_argument("--source", required=True, help="collection di partenza (non viene modificata)")
    ap.add_argument("--target", help="collection da creare con le date; senza, solo anteprima")
    ap.add_argument("--raw-dir", default="data/raw", help="cartella dei documenti salvati dal crawler")
    ap.add_argument("--site-dates", default=site_dates_settings()["path"],
                    help="mappa URL -> data di scripts/fetch_site_dates.py (se manca si usano solo le euristiche)")
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()

    client = QdrantClientManager().get_client()
    existing = {c.name for c in client.get_collections().collections}
    if args.source not in existing:
        sys.exit(f"collection di partenza '{args.source}' non trovata")
    if args.target and args.target in existing:
        sys.exit(f"'{args.target}' esiste gia': non la sovrascrivo")

    points = read_points(client, args.source, with_vectors=bool(args.target))
    sources = {(p.payload or {}).get("source", "") for p in points} - {""}
    site_dates = load_site_dates(args.site_dates, site_dates_settings()["sections"])
    print(f"mappa delle date dalla ricerca del sito: {len(site_dates)} pagine nelle sezioni datate ({args.site_dates})")
    if not site_dates:
        print("  (assente: lancia prima scripts/fetch_site_dates.py per le date esatte)")
    dates, url_only = dates_for_sources(sources, Path(args.raw_dir), site_dates)
    report(points, dates, url_only)

    if not args.target:
        print("\nAnteprima: nessuna collection creata. Aggiungi --target per creare la copia con le date.")
        client.close()
        return

    vectors = points[0].vector
    dense = vectors[DENSE_VECTOR] if isinstance(vectors, dict) else vectors
    if not isinstance(vectors, dict):
        sys.exit("la collection di partenza ha un solo vettore anonimo: serve una collection ibrida (denso + BM25)")
    info = client.get_collection(args.source)
    metadata = dict(getattr(info.config, "metadata", None) or {})
    metadata["dates"] = {"source_collection": args.source, "raw_dir": args.raw_dir}
    client.create_collection(collection_name=args.target, **collection_schema(len(dense)), metadata=metadata)

    for i in range(0, len(points), args.batch):
        batch = []
        for p in points[i:i + args.batch]:
            payload = {k: v for k, v in (p.payload or {}).items() if k not in DATE_KEYS}
            payload.update(dates.get(payload.get("source", ""), {}))
            batch.append(models.PointStruct(id=p.id, vector=p.vector, payload=payload))
        client.upsert(collection_name=args.target, points=batch)
    print(f"\n'{args.target}': {client.count(args.target).count} punti (attesi {len(points)})")
    client.close()


if __name__ == "__main__":
    main()
