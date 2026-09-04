#!/usr/bin/env python3
"""
Perche' due script danno numeri diversi per la stessa configurazione.

Il fatto
--------
Ablation del 27/08 e compare_embeddings del 28/08 girano sullo stesso indice
(13.784 chunk), con gli stessi parametri dichiarati (top_k=25, soglia 0,3,
filtro di categoria acceso, reranker bge-reranker-base -> 5). L'ablation
riceve 25 candidati su tutte e 30 le domande; compare_embeddings ne riceve in
media 9,4, e per sei domande zero. Le due misure non possono essere entrambe
corrette.

Le due differiscono in un punto solo: come viene vettorizzata la domanda.

    ablation            ModelFactory.create_embeddings().embed_query(q)
                        cioe' HuggingFaceEmbeddings, la stessa classe con cui
                        e' stato costruito l'indice

    compare_embeddings  SentenceTransformer(nome).encode(q, normalize=True)

Se i due vettori non coincidono, i punteggi di similarita' cambiano, la
`score_threshold` taglia in modo diverso e il numero di candidati crolla. Non
comparirebbe alcun errore: solo meno documenti, e metriche piu' basse.

Cosa misura questo script
-------------------------
1. Come e' fatta la collection: metrica di distanza e norma dei vettori
   memorizzati. Se la distanza fosse DOT e i vettori non normalizzati, i
   punteggi non sarebbero affatto coseni e la soglia 0,3 non avrebbe il
   significato che le attribuiamo.
2. Per alcune domande, i due vettori di query a confronto: norma di ciascuno e
   coseno fra loro. Un coseno di 1,000 significa che il percorso di
   vettorizzazione non c'entra e la causa e' altrove (classificatore, filtro).
3. Quanti candidati tornano con e senza soglia, e con e senza filtro di
   categoria, per ciascuno dei due vettori. Isola quale dei due meccanismi
   sta togliendo i documenti.

Non modifica nulla e non rivettorizza nulla. Richiede l'API spenta.

Uso:
    python benchmarks/diagnosi_soglia.py
    python benchmarks/diagnosi_soglia.py --limit 8
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()


def coseno(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return num / (na * nb) if na and nb else 0.0


def norma(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnosi della discrepanza fra ablation e compare_embeddings")
    ap.add_argument("--dataset", default="config/golden_dataset_v2.json")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    from qdrant_client.http import models as rest

    from src.core.config_loader import ConfigLoader
    from src.core.model_factory import ModelFactory
    from src.rag.query_classifier import QueryClassifier
    from src.vectorstore.qdrant_client import QdrantClientManager

    rag = ConfigLoader.get_rag_config()
    nome_modello = rag.get("embedding", {}).get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
    soglia = rag.get("retrieval", {}).get("score_threshold", 0.3)
    top_k = rag.get("retrieval", {}).get("top_k", 25)

    manager = QdrantClientManager()
    client = manager.get_client()
    coll = manager.collection_name
    info = client.get_collection(coll)

    console.print("\n[bold cyan]1 · Come e' fatta la collection[/bold cyan]")
    vettori_cfg = info.config.params.vectors
    distanza = getattr(vettori_cfg, "distance", None)
    dimensione = getattr(vettori_cfg, "size", None)
    console.print(f"   collection: [bold]{coll}[/bold] · punti: {info.points_count:,}")
    console.print(f"   distanza: [bold]{distanza}[/bold] · dimensione: {dimensione}")

    campione, _ = client.scroll(collection_name=coll, limit=5, with_vectors=True, with_payload=False)
    norme = [norma(p.vector) for p in campione if isinstance(p.vector, list)]
    if norme:
        console.print(f"   norma dei vettori memorizzati (5 campioni): "
                      f"{', '.join(f'{n:.4f}' for n in norme)}")
        if all(abs(n - 1.0) < 0.01 for n in norme):
            console.print("   [green]vettori normalizzati: il punteggio e' un coseno in [-1, 1][/green]")
        else:
            console.print("   [yellow]vettori NON normalizzati: con distanza DOT il punteggio non e' un "
                          "coseno e la soglia 0,3 non ha il significato che le attribuiamo[/yellow]")

    console.print("\n[bold cyan]2 · I due percorsi di vettorizzazione della query[/bold cyan]")
    console.print("[dim]caricamento HuggingFaceEmbeddings (percorso ablation / produzione)…[/dim]")
    hf = ModelFactory.create_embeddings()

    from sentence_transformers import SentenceTransformer
    nome_st = nome_modello if "/" in nome_modello else f"sentence-transformers/{nome_modello}"
    console.print(f"[dim]caricamento SentenceTransformer {nome_st} (percorso compare_embeddings)…[/dim]")
    st = SentenceTransformer(nome_st)

    qc = QueryClassifier()
    with open(args.dataset, encoding="utf-8") as fh:
        items = json.load(fh)["items"][: args.limit]

    t = Table(title="Confronto fra i due vettori di query", title_style="bold")
    for c in ("id", "categoria", "‖hf‖", "‖st‖", "coseno hf·st"):
        t.add_column(c)

    vettori = {}
    for it in items:
        q = it["question"]
        v_hf = hf.embed_query(q)
        v_st = st.encode(q, normalize_embeddings=True).tolist()
        vettori[it["id"]] = (v_hf, v_st, qc.classify(q))
        t.add_row(it["id"], vettori[it["id"]][2], f"{norma(v_hf):.4f}",
                  f"{norma(v_st):.4f}", f"{coseno(v_hf, v_st):.6f}")
    console.print(t)

    cosini = [coseno(v[0], v[1]) for v in vettori.values()]
    if all(c > 0.9999 for c in cosini):
        console.print("[green]I due percorsi producono lo stesso vettore: la causa NON e' la "
                      "vettorizzazione. Guardare la tabella 3 (soglia e filtro).[/green]")
    else:
        console.print(f"[red]I due percorsi producono vettori diversi (coseno minimo "
                      f"{min(cosini):.6f}). Uno dei due non corrisponde a come e' stato "
                      f"costruito l'indice, e i punteggi non sono confrontabili.[/red]")

    console.print("\n[bold cyan]3 · Chi toglie i documenti: la soglia o il filtro?[/bold cyan]")
    t = Table(title=f"Numero di candidati (top_k={top_k}, soglia={soglia})", title_style="bold")
    for c in ("id", "vettore", "senza soglia\nsenza filtro", "con soglia\nsenza filtro",
              "senza soglia\ncon filtro", "con soglia\ncon filtro", "punteggio 1º", "punteggio 25º"):
        t.add_column(c)

    for it in items:
        qid = it["id"]
        v_hf, v_st, categoria = vettori[qid]
        filtro = None
        if categoria != "generico":
            filtro = rest.Filter(must=[
                rest.FieldCondition(key="category", match=rest.MatchValue(value=categoria))
            ])

        for etichetta, vettore in (("hf", v_hf), ("st", v_st)):
            def conta(sog, filt):
                return client.query_points(collection_name=coll, query=vettore, limit=top_k,
                                           score_threshold=sog, query_filter=filt).points

            libero = conta(None, None)
            punteggi = [p.score for p in libero]
            t.add_row(
                qid if etichetta == "hf" else "",
                etichetta,
                str(len(libero)),
                str(len(conta(soglia, None))),
                str(len(conta(None, filtro))),
                str(len(conta(soglia, filtro))),
                f"{punteggi[0]:.4f}" if punteggi else "—",
                f"{punteggi[-1]:.4f}" if punteggi else "—",
            )
    console.print(t)

    console.print("\n[bold]Come leggere la tabella[/bold]")
    console.print("  · se «senza soglia» e' 25 e «con soglia» e' molto meno, taglia la soglia;")
    console.print("  · se «senza filtro» e' 25 e «con filtro» e' molto meno, taglia il filtro;")
    console.print("  · se le righe hf e st differiscono, i due script non stanno misurando la "
                  "stessa cosa e uno dei due risultati va scartato.\n")


if __name__ == "__main__":
    main()
