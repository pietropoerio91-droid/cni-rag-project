#!/usr/bin/env python3
"""Scarica la mappa URL -> data di pubblicazione dalla ricerca interna di cni.it.

Le pagine degli articoli non riportano la data; la ricerca del sito si'
(src/ingestion/site_dates.py). La mappa viene salvata in `dates.site_dates_file`
(config/rag_config.yaml) e usata da run_ingestion.py, build_index.py,
add_document_dates.py e dall'endpoint /ingest.

Usage:
    python scripts/fetch_site_dates.py
    python scripts/fetch_site_dates.py --output data/dates/site_dates.json --delay 1
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.site_dates import fetch_site_dates, save_site_dates, site_dates_settings


def main() -> None:
    s = site_dates_settings()
    ap = argparse.ArgumentParser(description="Mappa URL -> data dalla ricerca di cni.it")
    ap.add_argument("--output", default=s["path"])
    ap.add_argument("--delay", type=float, default=s["delay"], help="pausa fra le richieste (secondi)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    dates = fetch_site_dates(s["base_url"], s["terms"], args.delay)
    path = save_site_dates(dates, args.output)
    print(f"\n{len(dates)} pagine con data salvate in {path}")
    sections = Counter(v["url"].split("/")[3] if v["url"].count("/") > 3 else "/" for v in dates.values())
    print("sezioni:", ", ".join(f"{k} {n}" for k, n in sections.most_common(8)))
    print("anni:   ", " ".join(f"{y}:{n}" for y, n in sorted(Counter(v["date"][:4] for v in dates.values()).items())))


if __name__ == "__main__":
    main()
