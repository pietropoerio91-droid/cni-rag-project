#!/usr/bin/env python3
"""
Diagnostica del sistema: tre misure che vanno agli atti prima degli esperimenti.

Nessuna di queste richiede l'LLM o l'API: girano in pochi minuti e producono
dati riportabili in tesi.

  1. TRONCAMENTO DEI CHUNK
     Il modello di embedding ha un limite di token (max_seq_length). Se i
     chunk lo superano, la parte eccedente viene scartata SILENZIOSAMENTE
     prima di produrre il vettore: il retrieval ordina i documenti sulla base
     di una frazione del loro contenuto.
     paraphrase-multilingual-MiniLM-L12-v2 dichiara 128 token; i chunk sono
     da 1500 caratteri. Questa misura dice quanto se ne perde davvero.

  2. COPERTURA DELLE CATEGORIE
     L'ingestion assegna una categoria in base a pattern sull'URL, e a
     runtime il retrieval filtra rigidamente su quella categoria. Un chunk
     senza categoria non ha il campo nel payload: e' quindi invisibile a
     qualunque query classificata. Questa misura conta quanti sono.

  3. OCCUPAZIONE DI MEMORIA
     Quanto occupano davvero i modelli caricati insieme. Serve a sostituire
     con misure le stime sul budget degli 8 GB.

Usage:
    python benchmarks/diagnostics.py                 # tutte
    python benchmarks/diagnostics.py --only tokens
    python benchmarks/diagnostics.py --only categories
    python benchmarks/diagnostics.py --only memory
    python benchmarks/diagnostics.py --sample 500    # chunk da campionare
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from src.core.config_loader import ConfigLoader

console = Console()
OUT_DIR = Path("results")


# ---------------------------------------------------------------------------
# Accesso ai chunk indicizzati
# ---------------------------------------------------------------------------

def scroll_chunks(limit: int | None = None) -> list[dict[str, Any]]:
    """Legge i chunk direttamente da Qdrant, con payload."""
    from src.vectorstore.qdrant_client import QdrantClientManager

    manager = QdrantClientManager()
    client = manager.get_client()
    collection = manager.collection_name

    out: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            out.append(dict(p.payload or {}))
            if limit and len(out) >= limit:
                return out
        if offset is None:
            break
    return out


# ---------------------------------------------------------------------------
# 1. Troncamento
# ---------------------------------------------------------------------------

def check_truncation(sample: int) -> dict[str, Any]:
    console.print("\n[bold cyan]1. Troncamento dei chunk in fase di embedding[/bold cyan]")

    model_name = ConfigLoader.get_rag_config().get("embedding", {}).get(
        "model_name", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    if "/" not in model_name:
        model_name = f"sentence-transformers/{model_name}"

    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(model_name)
    except Exception as exc:
        console.print(f"[red]Impossibile caricare il tokenizzatore di {model_name}: {exc}[/red]")
        return {"error": str(exc)}

    # Il limite vero e' quello di sentence-transformers, non del tokenizzatore.
    max_seq = None
    try:
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(model_name)
        max_seq = st.max_seq_length
        del st
    except Exception:
        pass
    if not max_seq or max_seq > 100000:
        max_seq = min(getattr(tok, "model_max_length", 512) or 512, 512)

    console.print(f"   modello: [bold]{model_name}[/bold]")
    console.print(f"   max_seq_length effettivo: [bold]{max_seq}[/bold] token")

    chunks = scroll_chunks(limit=sample)
    testi = [c.get("content", "") for c in chunks if c.get("content")]
    if not testi:
        console.print("[red]Nessun chunk trovato nell'indice.[/red]")
        return {"error": "indice vuoto"}

    counts = [len(tok.encode(t, add_special_tokens=True)) for t in testi]
    chars = [len(t) for t in testi]

    oltre = sum(1 for c in counts if c > max_seq)
    persa = [max(0, c - max_seq) / c for c in counts]

    res = {
        "model": model_name,
        "max_seq_length": max_seq,
        "n_chunk_campionati": len(counts),
        "caratteri_mediana": round(statistics.median(chars), 1),
        "token_mediana": round(statistics.median(counts), 1),
        "token_media": round(statistics.mean(counts), 1),
        "token_min": min(counts),
        "token_max": max(counts),
        "caratteri_per_token": round(statistics.mean(chars) / statistics.mean(counts), 2),
        "chunk_troncati": oltre,
        "chunk_troncati_pct": round(100 * oltre / len(counts), 1),
        "frazione_media_persa_pct": round(100 * statistics.mean(persa), 1),
        "porzione_vista_dal_modello_pct": round(100 * min(1.0, max_seq / statistics.mean(counts)), 1),
    }

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("chunk campionati", f"{res['n_chunk_campionati']}")
    t.add_row("caratteri per chunk (mediana)", f"{res['caratteri_mediana']:.0f}")
    t.add_row("token per chunk (mediana)", f"{res['token_mediana']:.0f}")
    t.add_row("caratteri per token", f"{res['caratteri_per_token']}")
    t.add_row("[bold]chunk troncati[/bold]",
              f"[bold]{res['chunk_troncati']}/{res['n_chunk_campionati']} = {res['chunk_troncati_pct']}%[/bold]")
    t.add_row("[bold]porzione media scartata[/bold]", f"[bold]{res['frazione_media_persa_pct']}%[/bold]")
    console.print(t)

    if res["chunk_troncati_pct"] > 50:
        console.print(
            f"\n   [red]Il modello vede in media il {res['porzione_vista_dal_modello_pct']}% "
            f"di ogni chunk.[/red] L'ordinamento semantico si basa su quella frazione."
        )
    elif res["chunk_troncati_pct"] > 5:
        console.print(f"\n   [yellow]Troncamento presente ma parziale.[/yellow]")
    else:
        console.print("\n   [green]Nessun troncamento significativo.[/green]")

    # Cosa c'e' all'inizio dei chunk: i primi token sono gli unici che contano
    console.print("\n   [dim]Primi 90 caratteri di 5 chunk (cio' che il modello vede per primo):[/dim]")
    for t_ in testi[:5]:
        console.print(f"   [dim]· {t_[:90].replace(chr(10), ' ')}…[/dim]")

    return res


# ---------------------------------------------------------------------------
# 2. Copertura delle categorie
# ---------------------------------------------------------------------------

def check_categories() -> dict[str, Any]:
    console.print("\n[bold cyan]2. Copertura delle categorie nell'indice[/bold cyan]")

    chunks = scroll_chunks()
    if not chunks:
        console.print("[red]Nessun chunk trovato.[/red]")
        return {"error": "indice vuoto"}

    counter = Counter((c.get("category") or "__SENZA_CATEGORIA__") for c in chunks)
    tot = sum(counter.values())
    senza = counter.get("__SENZA_CATEGORIA__", 0)

    t = Table(title=f"Chunk per categoria (totale {tot})", title_style="bold")
    t.add_column("categoria")
    t.add_column("chunk", justify="right")
    t.add_column("%", justify="right")
    for cat, n in counter.most_common():
        label = "[red]SENZA CATEGORIA[/red]" if cat == "__SENZA_CATEGORIA__" else cat
        t.add_row(label, str(n), f"{100*n/tot:.1f}%")
    console.print(t)

    # Quali categorie il classificatore di query puo' effettivamente produrre
    from src.rag.query_classifier import QueryClassifier
    producibili = set(QueryClassifier.CATEGORIES.keys())
    presenti = {c for c in counter if c != "__SENZA_CATEGORIA__"}

    mai_richieste = presenti - producibili
    mai_presenti = producibili - presenti

    console.print(f"\n   categorie nell'indice: [bold]{len(presenti)}[/bold]")
    console.print(f"   categorie che il classificatore puo' produrre: [bold]{len(producibili)}[/bold]")

    if mai_richieste:
        n_orfani = sum(counter[c] for c in mai_richieste)
        console.print(
            f"\n   [yellow]{len(mai_richieste)} categorie non sono mai richiedibili dal classificatore[/yellow]"
            f" ({', '.join(sorted(mai_richieste))}) — {n_orfani} chunk ({100*n_orfani/tot:.1f}%)"
            f"\n   raggiungibili solo dalle query classificate 'generico'."
        )
    if mai_presenti:
        console.print(
            f"\n   [red]{len(mai_presenti)} categorie sono producibili dal classificatore ma NON esistono "
            f"nell'indice[/red] ({', '.join(sorted(mai_presenti))})."
            f"\n   Una query che finisce in una di queste restituisce ZERO documenti."
        )
    if senza:
        console.print(
            f"\n   [red]{senza} chunk ({100*senza/tot:.1f}%) non hanno categoria[/red]: "
            f"invisibili a qualunque query classificata."
        )

    return {
        "totale_chunk": tot,
        "per_categoria": dict(counter),
        "senza_categoria": senza,
        "senza_categoria_pct": round(100 * senza / tot, 2),
        "categorie_non_richiedibili": sorted(mai_richieste),
        "categorie_richieste_ma_assenti": sorted(mai_presenti),
    }


# ---------------------------------------------------------------------------
# 3. Memoria
# ---------------------------------------------------------------------------

def check_memory() -> dict[str, Any]:
    console.print("\n[bold cyan]3. Occupazione di memoria dei modelli[/bold cyan]")

    try:
        import psutil
    except ImportError:
        console.print("[yellow]psutil non installato: pip install psutil[/yellow]")
        return {"error": "psutil mancante"}

    proc = psutil.Process()
    mb = lambda: proc.memory_info().rss / 1024 / 1024  # noqa: E731

    steps: list[tuple[str, float]] = [("processo Python a vuoto", mb())]

    from src.core.model_factory import ModelFactory
    emb = ModelFactory.create_embeddings()
    emb.embed_query("prova")
    steps.append(("+ modello di embedding", mb()))

    cfg = ConfigLoader.get_rag_config()
    rer_name = cfg.get("reranking", {}).get("model", "BAAI/bge-reranker-base")
    try:
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(rer_name)
        ce.predict([("domanda di prova", "documento di prova")])
        steps.append(("+ reranker cross-encoder", mb()))
    except Exception as exc:
        console.print(f"   [yellow]reranker non caricato: {exc}[/yellow]")

    try:
        from src.vectorstore.qdrant_client import QdrantClientManager
        QdrantClientManager().get_client().get_collections()
        steps.append(("+ client Qdrant", mb()))
    except Exception as exc:
        console.print(f"   [yellow]Qdrant non raggiungibile: {exc}[/yellow]")

    t = Table(title="Memoria residente del processo", title_style="bold")
    t.add_column("dopo aver caricato")
    t.add_column("RSS (MB)", justify="right")
    t.add_column("delta (MB)", justify="right")
    prev = None
    for label, val in steps:
        t.add_row(label, f"{val:,.0f}", f"+{val-prev:,.0f}" if prev is not None else "—")
        prev = val
    console.print(t)

    vm = psutil.virtual_memory()
    console.print(
        f"\n   RAM totale di sistema: [bold]{vm.total/1024**3:.1f} GB[/bold] · "
        f"disponibile ora: [bold]{vm.available/1024**3:.1f} GB[/bold] · "
        f"in uso: {vm.percent:.0f}%"
    )
    console.print(
        "   [dim]Nota: il modello generativo gira in un processo separato (Ollama) "
        "e non compare in questa misura.[/dim]"
    )

    return {
        "steps": [{"dopo": l, "rss_mb": round(v, 1)} for l, v in steps],
        "ram_totale_gb": round(vm.total / 1024**3, 2),
        "ram_disponibile_gb": round(vm.available / 1024**3, 2),
        "ram_usata_pct": vm.percent,
    }


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostica del sistema RAG CNI")
    parser.add_argument("--only", choices=["tokens", "categories", "memory"], default=None)
    parser.add_argument("--sample", type=int, default=1000, help="Chunk da campionare per il troncamento")
    args = parser.parse_args()

    console.print("[bold]Diagnostica RAG CNI[/bold]")
    report: dict[str, Any] = {"data": datetime.now().isoformat(timespec="seconds")}

    if args.only in (None, "tokens"):
        report["troncamento"] = check_truncation(args.sample)
    if args.only in (None, "categories"):
        report["categorie"] = check_categories()
    if args.only in (None, "memory"):
        report["memoria"] = check_memory()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"diagnostics_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    console.print(f"\n[green]Report salvato in:[/green] {out}")


if __name__ == "__main__":
    main()
