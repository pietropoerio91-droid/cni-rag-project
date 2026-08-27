#!/usr/bin/env python3
"""
Confronto sperimentale fra modelli di embedding, sullo stesso corpus.

Il problema che lo motiva
-------------------------
`benchmarks/diagnostics.py` ha misurato che paraphrase-multilingual-MiniLM-L12-v2
tronca a 128 token, mentre i chunk hanno una mediana di 266 token: l'82% dei
chunk viene tagliato e in media il 41% del contenuto non arriva mai al vettore.
Il retrieval ordina quindi i documenti su una frazione arbitraria del loro
testo — i primi 128 token, qualunque cosa contengano.

Un modello con finestra piu' ampia eliminerebbe il troncamento, ma la
sostituzione va DIMOSTRATA, non assunta: modelli diversi differiscono anche
per obiettivo di addestramento e per lingua, e un cambio potrebbe peggiorare.

Cosa fa
-------
  1. rilegge tutti i chunk gia' indicizzati da Qdrant (nessun ricrawl, nessun
     ri-chunking: si riusa esattamente lo stesso testo)
  2. li rivettorizza con ciascun modello candidato in una collection SEPARATA
     (l'indice originale non viene mai toccato)
  3. valuta il retrieval sul golden dataset per ogni modello
  4. confronta con test appaiati, IC 95% e dimensione dell'effetto

Prefissi dei modelli E5
-----------------------
La famiglia multilingual-e5 e' addestrata con prefissi asimmetrici: le query
vanno precedute da "query: " e i documenti da "passage: ". Ometterli degrada
sensibilmente le prestazioni. Sono gestiti automaticamente per modello.

Usage:
    python benchmarks/compare_embeddings.py                    # indicizza e confronta
    python benchmarks/compare_embeddings.py --skip-index       # solo confronto
    python benchmarks/compare_embeddings.py --models intfloat/multilingual-e5-small
    python benchmarks/compare_embeddings.py --markdown
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from benchmarks import metrics as M
from benchmarks import stats as S
from src.core.config_loader import ConfigLoader

console = Console()
RESULTS_DIR = Path("results")
K_VALUES = (1, 3, 5, 10)

# Prefissi richiesti dal modello. Chiave: sottostringa del nome del modello.
PREFISSI: dict[str, tuple[str, str]] = {
    "e5": ("query: ", "passage: "),
    "bge-m3": ("", ""),
    "gte": ("", ""),
}

CANDIDATI_DEFAULT = [
    "intfloat/multilingual-e5-small",
]


def prefissi_per(modello: str) -> tuple[str, str]:
    for chiave, val in PREFISSI.items():
        if chiave in modello.lower():
            return val
    return ("", "")


def slug(modello: str) -> str:
    return modello.split("/")[-1].replace(".", "_").replace("-", "_").lower()


# ---------------------------------------------------------------------------

def leggi_chunk(manager, collection: str) -> list[dict[str, Any]]:
    """Rilegge tutti i chunk indicizzati, con testo e payload."""
    client = manager.get_client()
    out, offset = [], None
    while True:
        punti, offset = client.scroll(
            collection_name=collection, limit=1000, offset=offset,
            with_payload=True, with_vectors=False,
        )
        out.extend({"payload": dict(p.payload or {})} for p in punti)
        if offset is None:
            break
    return [c for c in out if (c["payload"].get("content") or "").strip()]


def indicizza(manager, chunks: list[dict[str, Any]], modello: str, batch: int = 32) -> str:
    """Rivettorizza i chunk con `modello` in una collection separata."""
    from qdrant_client.http import models as rest
    from qdrant_client.http.models import PointStruct
    from sentence_transformers import SentenceTransformer

    nome = f"cni_emb_{slug(modello)}"
    client = manager.get_client()

    console.print(f"   caricamento [bold]{modello}[/bold]…")
    st = SentenceTransformer(modello)
    dim = st.get_sentence_embedding_dimension()
    console.print(f"   dimensione vettore: [bold]{dim}[/bold] · finestra: [bold]{st.max_seq_length}[/bold] token")

    esistenti = {c.name for c in client.get_collections().collections}
    if nome in esistenti:
        client.delete_collection(nome)
    client.create_collection(
        collection_name=nome,
        vectors_config=rest.VectorParams(size=dim, distance=rest.Distance.COSINE),
    )

    _, pref_doc = prefissi_per(modello)
    testi = [c["payload"]["content"] for c in chunks]

    t0 = time.perf_counter()
    with Progress(TextColumn("   [progress.description]{task.description}"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  TimeRemainingColumn(), console=console) as prog:
        task = prog.add_task("vettorizzazione", total=len(testi))
        for i in range(0, len(testi), batch):
            blocco = testi[i: i + batch]
            vettori = st.encode(
                [pref_doc + t for t in blocco],
                normalize_embeddings=True, show_progress_bar=False, batch_size=batch,
            )
            client.upsert(collection_name=nome, points=[
                PointStruct(id=str(uuid.uuid4()), vector=v.tolist(), payload=chunks[i + j]["payload"])
                for j, v in enumerate(vettori)
            ])
            prog.update(task, advance=len(blocco))

    durata = time.perf_counter() - t0
    console.print(f"   [green]{len(testi)} chunk indicizzati in {durata/60:.1f} min[/green] "
                  f"({len(testi)/max(1,durata):.0f} chunk/s) → collection [bold]{nome}[/bold]")
    del st
    return nome


# ---------------------------------------------------------------------------

def valuta(manager, collection: str, modello: str, items: list[dict],
           top_k: int, soglia: float, filtro_categoria: bool,
           reranker_nome: str | None, rerank_top_k: int) -> dict[str, Any]:
    """Retrieval + rerank opzionale sulle domande del golden dataset."""
    from sentence_transformers import SentenceTransformer
    from src.rag.query_classifier import QueryClassifier

    st = SentenceTransformer(modello)
    qc = QueryClassifier()
    client = manager.get_client()
    pref_q, _ = prefissi_per(modello)

    ce = None
    if reranker_nome:
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(reranker_nome)

    per_domanda, t0 = [], time.perf_counter()
    for it in items:
        domanda = it["question"]
        categoria = qc.classify(domanda)

        filtro = None
        if filtro_categoria and categoria != "generico":
            from qdrant_client.http import models as rest
            filtro = rest.Filter(must=[
                rest.FieldCondition(key="category", match=rest.MatchValue(value=categoria))
            ])

        vettore = st.encode(pref_q + domanda, normalize_embeddings=True).tolist()
        punti = client.query_points(
            collection_name=collection, query=vettore, limit=top_k,
            score_threshold=soglia, query_filter=filtro,
        ).points

        candidati = [{
            "content": p.payload.get("content", ""),
            "source": p.payload.get("source", ""),
            "title": p.payload.get("title", ""),
            "score": p.score,
        } for p in punti]

        if ce and candidati:
            punteggi = ce.predict([(domanda, c["content"]) for c in candidati])
            ordinati = sorted(zip(candidati, punteggi), key=lambda x: x[1], reverse=True)
            contesto = [c for c, _ in ordinati[:rerank_top_k]]
        else:
            contesto = candidati[:rerank_top_k]

        stadi = M.evaluate_stages(candidati, contesto, it.get("expected_sources", []), K_VALUES)
        per_domanda.append({
            "question_id": it["id"],
            "n_candidati": len(candidati),
            "retrieved": stadi["retrieved"],
            "context": stadi["context"],
        })

    del st
    pre = [r["retrieved"] for r in per_domanda]
    post = [r["context"] for r in per_domanda]
    chiavi = ["mrr"] + [f"{m}_at_{k}" for k in K_VALUES for m in ("hit", "recall", "ndcg")]

    return {
        "modello": modello,
        "collection": collection,
        "finestra_token": None,
        "durata_s": round(time.perf_counter() - t0, 1),
        "candidati_medi": round(sum(r["n_candidati"] for r in per_domanda) / max(1, len(per_domanda)), 1),
        "domande_senza_candidati": sum(1 for r in per_domanda if r["n_candidati"] == 0),
        "punto_context": M.aggregate_rankings(post, K_VALUES),
        "ci_retrieved": {c: S.summarize_metric(M.column(pre, c), c, binary=c.startswith("hit")) for c in chiavi},
        "ci_context": {c: S.summarize_metric(M.column(post, c), c, binary=c.startswith("hit")) for c in chiavi},
        "per_domanda": per_domanda,
    }


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Confronto fra modelli di embedding")
    ap.add_argument("--dataset", default="config/golden_dataset_v2.json")
    ap.add_argument("--models", nargs="*", default=CANDIDATI_DEFAULT,
                    help="modelli candidati da confrontare con quello attuale")
    ap.add_argument("--skip-index", action="store_true",
                    help="non rivettorizzare: usa collection gia' create")
    ap.add_argument("--no-filter", action="store_true",
                    help="disattiva il filtro di categoria (esclude il 75%% dell'indice)")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data["items"][: args.limit] if args.limit else data["items"]

    rag = ConfigLoader.get_rag_config()
    attuale = rag.get("embedding", {}).get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
    if "/" not in attuale:
        attuale = f"sentence-transformers/{attuale}"
    top_k = rag.get("retrieval", {}).get("top_k", 25)
    soglia = rag.get("retrieval", {}).get("score_threshold", 0.3)
    reranker = None if args.no_rerank else rag.get("reranking", {}).get("model")
    rerank_top_k = rag.get("reranking", {}).get("top_k", 5)
    filtro = not args.no_filter

    from src.vectorstore.qdrant_client import QdrantClientManager
    manager = QdrantClientManager()
    base_collection = manager.collection_name

    console.print("\n[bold cyan]Confronto fra modelli di embedding[/bold cyan]")
    console.print(f"attuale: [bold]{attuale}[/bold]")
    console.print(f"candidati: {', '.join(args.models)}")
    console.print(f"domande: [bold]{len(items)}[/bold] · top_k={top_k} · "
                  f"filtro categoria={'sì' if filtro else 'no'} · "
                  f"rerank={reranker.split('/')[-1] if reranker else 'no'}\n")

    chunks = []
    if not args.skip_index:
        console.print("[dim]rilettura dei chunk indicizzati…[/dim]")
        chunks = leggi_chunk(manager, base_collection)
        console.print(f"[dim]{len(chunks)} chunk letti da '{base_collection}'[/dim]\n")

    risultati = []

    console.print("[cyan]1[/cyan] modello attuale — nessuna reindicizzazione")
    r = valuta(manager, base_collection, attuale, items, top_k, soglia, filtro, reranker, rerank_top_k)
    r["nome"] = "attuale"
    risultati.append(r)
    console.print(f"   Hit@5 {S.format_ci(r['ci_context']['hit_at_5'], pct=True)} · "
                  f"MRR {S.format_ci(r['ci_context']['mrr'])}\n")

    for i, modello in enumerate(args.models, 2):
        console.print(f"[cyan]{i}[/cyan] {modello}")
        nome_coll = f"cni_emb_{slug(modello)}"
        if not args.skip_index:
            nome_coll = indicizza(manager, chunks, modello)
        r = valuta(manager, nome_coll, modello, items, top_k, soglia, filtro, reranker, rerank_top_k)
        r["nome"] = modello.split("/")[-1]
        risultati.append(r)
        console.print(f"   Hit@5 {S.format_ci(r['ci_context']['hit_at_5'], pct=True)} · "
                      f"MRR {S.format_ci(r['ci_context']['mrr'])}\n")

    # --- tabella -----------------------------------------------------------
    t = Table(title=f"Contesto passato al generatore — n={len(items)}, IC 95%", title_style="bold")
    t.add_column("modello")
    for c in ("Hit@3", "Hit@5", "MRR", "Recall@5", "nDCG@5"):
        t.add_column(c, justify="right")
    for r in risultati:
        c = r["ci_context"]
        t.add_row(r["nome"],
                  S.format_ci(c["hit_at_3"], pct=True), S.format_ci(c["hit_at_5"], pct=True),
                  S.format_ci(c["mrr"]), S.format_ci(c["recall_at_5"]), S.format_ci(c["ndcg_at_5"]))
    console.print(t)

    # --- confronti appaiati ------------------------------------------------
    base = risultati[0]
    confronti = {}
    if len(risultati) > 1:
        ct = Table(title=f"Confronto appaiato contro «{base['nome']}»", title_style="bold")
        ct.add_column("modello")
        for c in ("Δ Hit@5", "p", "Δ MRR", "p", "Δ nDCG@5", "effetto"):
            ct.add_column(c, justify="right")
        for r in risultati[1:]:
            cmp_ = {}
            for chiave, binaria in [("hit_at_5", True), ("mrr", False), ("ndcg_at_5", False)]:
                a = M.column([x["context"] for x in base["per_domanda"]], chiave)
                b = M.column([x["context"] for x in r["per_domanda"]], chiave)
                cmp_[chiave] = S.paired_report(a, b, name=chiave, binary=binaria,
                                               label_a="attuale", label_b="candidato")
            confronti[r["nome"]] = cmp_
            h, m, n = cmp_["hit_at_5"], cmp_["mrr"], cmp_["ndcg_at_5"]
            ct.add_row(r["nome"],
                       f"{h['mean_difference']:+.3f}", f"{h['significance']['p_value']:.4f}",
                       f"{m['mean_difference']:+.3f}", f"{m['significance']['p_value']:.4f}",
                       f"{n['mean_difference']:+.3f}", m["effect_size"]["magnitude"])
        console.print()
        console.print(ct)

        console.print(
            "\n[dim]Δ positivo = il candidato fa meglio dell'attuale. Con n=30 e un effetto "
            "piccolo il p-value puo' restare sopra 0,05 anche a fronte di un miglioramento "
            "reale: guardare anche il segno e l'ampiezza dell'IC sulla differenza.[/dim]"
        )

    # --- salvataggio -------------------------------------------------------
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"compare_embeddings_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "data": datetime.now().isoformat(timespec="seconds"),
            "dataset": args.dataset,
            "n_domande": len(items),
            "parametri": {"top_k": top_k, "soglia": soglia, "filtro_categoria": filtro,
                          "reranker": reranker, "rerank_top_k": rerank_top_k},
            "risultati": risultati,
            "confronti_vs_attuale": confronti,
            "ambiente_statistico": S.describe_environment(),
        }, fh, ensure_ascii=False, indent=2)
    console.print(f"\n[green]Salvato in:[/green] {out}")
    console.print("[dim]L'indice originale non e' stato modificato: le nuove collection sono separate.[/dim]")
    console.print("[dim]Per adottare un modello: aggiorna embedding.model_name in config/rag_config.yaml "
                  "e reindicizza la collection principale.[/dim]")

    if args.markdown:
        console.print("\n[bold]Tabella per la tesi[/bold]\n")
        print("| Modello di embedding | Hit@3 | Hit@5 | MRR | nDCG@5 |")
        print("|---|---|---|---|---|")
        for r in risultati:
            c = r["ci_context"]
            print(f"| {r['nome']} | {S.format_ci(c['hit_at_3'], pct=True)} | "
                  f"{S.format_ci(c['hit_at_5'], pct=True)} | {S.format_ci(c['mrr'])} | "
                  f"{S.format_ci(c['ndcg_at_5'])} |")
        print(f"\nn = {len(items)} domande · IC 95% · stesso corpus, stesso chunking, "
              f"stesso reranker · differenze valutate con test appaiati")


if __name__ == "__main__":
    main()
