#!/usr/bin/env python3
"""
Rimuove dall'indice i chunk delle pagine in lingua inglese.

Perche'
-------
Il crawler esclude gia' i percorsi `/en/` — vedi `CNICrawler.DENIED_PATTERNS`,
regola introdotta il 2 luglio 2026. L'indice attuale e' pero' anteriore a
quella modifica e contiene ancora 3.361 chunk su 17.145 (19,6%) provenienti
dalla versione inglese del sito.

Non e' un difetto del codice: e' un indice stantio rispetto alla
configurazione che lo governa. Questo script allinea l'indice a una regola
gia' decisa dal progetto, senza dover rifare il crawling.

Perche' conta per il retrieval
------------------------------
Ogni pagina inglese e' la traduzione di una pagina italiana gia' indicizzata:
nello spazio vettoriale i due chunk sono quasi sovrapposti e competono per gli
stessi posti nel top-k. Un duplicato che occupa una posizione ne toglie una a
un documento diverso, restringendo di fatto la varieta' dei candidati.

Sicurezza
---------
Il default e' `--dry-run`: conta e mostra un campione senza modificare nulla.
La cancellazione richiede `--apply` esplicito, e conviene comunque fare una
copia della cartella dell'indice prima:

    cp -R data/qdrant_db data/qdrant_db.backup

Usage:
    python scripts/purge_english_chunks.py                 # dry run
    python scripts/purge_english_chunks.py --apply
    python scripts/purge_english_chunks.py --pattern /en/ --pattern /fr/
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()


def main() -> None:
    ap = argparse.ArgumentParser(description="Rimuove i chunk in lingua inglese dall'indice")
    ap.add_argument("--pattern", action="append", default=None,
                    help="frammento di URL da rimuovere (ripetibile). Default: /en/")
    ap.add_argument("--apply", action="store_true",
                    help="esegue la cancellazione. Senza questo flag non modifica nulla.")
    args = ap.parse_args()

    patterns = [p.lower() for p in (args.pattern or ["/en/"])]

    from src.vectorstore.qdrant_client import QdrantClientManager

    manager = QdrantClientManager()
    client = manager.get_client()
    collection = manager.collection_name

    console.print(f"\n[bold cyan]Pulizia dell'indice[/bold cyan]  collection: [bold]{collection}[/bold]")
    console.print(f"pattern: {', '.join(patterns)}\n")

    da_togliere, tenuti = [], 0
    per_categoria: Counter = Counter()
    esempi: list[str] = []
    offset = None

    while True:
        punti, offset = client.scroll(
            collection_name=collection, limit=1000, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in punti:
            src = (p.payload or {}).get("source") or ""
            if any(pat in src.lower() for pat in patterns):
                da_togliere.append(p.id)
                per_categoria[(p.payload or {}).get("category") or "—"] += 1
                if len(esempi) < 5:
                    esempi.append(src)
            else:
                tenuti += 1
        if offset is None:
            break

    totale = len(da_togliere) + tenuti
    if not da_togliere:
        console.print("[green]Nessun chunk corrispondente: l'indice e' gia' pulito.[/green]")
        return

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("chunk totali", f"{totale:,}")
    t.add_row("[red]da rimuovere[/red]", f"[red]{len(da_togliere):,} ({100*len(da_togliere)/totale:.1f}%)[/red]")
    t.add_row("[green]che restano[/green]", f"[green]{tenuti:,}[/green]")
    console.print(t)

    ct = Table(title="Distribuzione per categoria dei chunk rimossi", title_style="bold")
    ct.add_column("categoria"); ct.add_column("chunk", justify="right")
    for cat, n in per_categoria.most_common(10):
        ct.add_row(cat, str(n))
    console.print()
    console.print(ct)

    console.print("\n[dim]Esempi di fonti rimosse:[/dim]")
    for e in esempi:
        console.print(f"[dim]  · {e}[/dim]")

    if not args.apply:
        console.print("\n[yellow]Modalita' di prova: non e' stato modificato nulla.[/yellow]")
        console.print("Per eseguire davvero:")
        console.print("  [cyan]cp -R data/qdrant_db data/qdrant_db.backup[/cyan]")
        console.print("  [cyan]python scripts/purge_english_chunks.py --apply[/cyan]")
        return

    console.print(f"\n[bold red]Rimozione di {len(da_togliere):,} chunk in corso…[/bold red]")
    BLOCCO = 500
    for i in range(0, len(da_togliere), BLOCCO):
        client.delete(collection_name=collection, points_selector=da_togliere[i: i + BLOCCO])
        console.print(f"  {min(i+BLOCCO, len(da_togliere)):,}/{len(da_togliere):,}", end="\r")

    rimasti = client.get_collection(collection).points_count
    console.print(f"\n[green]Fatto.[/green] L'indice contiene ora [bold]{rimasti:,}[/bold] chunk "
                  f"(erano {totale:,}).")

    reg = Path("results") / f"purge_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    with open(reg, "w", encoding="utf-8") as fh:
        json.dump({
            "data": datetime.now().isoformat(timespec="seconds"),
            "collection": collection,
            "pattern": patterns,
            "chunk_prima": totale,
            "chunk_rimossi": len(da_togliere),
            "chunk_dopo": rimasti,
            "per_categoria": dict(per_categoria),
            "esempi": esempi,
            "motivo": ("Allineamento dell'indice a CNICrawler.DENIED_PATTERNS, che esclude "
                       "i percorsi /en/ dal 2 luglio 2026. L'indice era anteriore a quella "
                       "regola."),
        }, fh, ensure_ascii=False, indent=2)
    console.print(f"[green]Registro dell'operazione:[/green] {reg}")
    console.print("\n[yellow]Rilancia l'ablation per misurare l'effetto della pulizia.[/yellow]")


if __name__ == "__main__":
    main()
