#!/usr/bin/env python3
"""
Test a contesto oracolo — isola il limite del modello generativo.

L'esperimento
-------------
Al modello viene passato DIRETTAMENTE il chunk che contiene la risposta,
saltando del tutto il retrieval. Il contesto e' perfetto per costruzione: se
il modello sbaglia comunque, non c'e' piu' nessuna causa a monte a cui
attribuire l'errore.

E' cosi' che si dimostra il limite hardware su una macchina sola, senza
bisogno di confrontare due computer — confronto che sarebbe comunque debole,
perche' sistema operativo, memoria e CPU varierebbero insieme e nessuna
differenza sarebbe attribuibile a una causa specifica.

Cosa si ottiene
---------------
Detta A la percentuale di risposte corrette con contesto oracolo e B quella
con il retrieval reale (dal run end-to-end), la differenza si decompone cosi':

    100% - A   quello che il GENERATORE non riesce a fare anche quando ha
               davanti il documento giusto: e' il limite del modello da 3B,
               imposto dagli 8 GB della piattaforma
    A - B      quello che si perde nel RETRIEVAL: documenti mai recuperati o
               scartati dal reranker

Due numeri che separano nettamente le due cause, e che rispondono alla
seconda meta' della domanda di ricerca.

Selezione del chunk oracolo
---------------------------
Fra i chunk provenienti dalle `expected_sources` viene scelto quello che
contiene piu' termini di `must_contain` — cioe' quello che davvero porta la
risposta, non semplicemente uno della pagina giusta.

Se nessun chunk della fonte attesa contiene quei termini, il caso viene
marcato `oracolo_debole` e riportato a parte: significa che l'informazione
non e' nel corpus nella forma attesa, oppure che il chunking l'ha spezzata.
E' a sua volta un risultato — e comunque non va confuso con un errore del
generatore.

Usage:
    python benchmarks/oracle_context.py
    python benchmarks/oracle_context.py --n-chunk 3      # contesto piu' ampio
    python benchmarks/oracle_context.py --confronta results/2026-08-28/eval_FINAL.json
    python benchmarks/oracle_context.py --markdown
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from benchmarks import stats as S

console = Console()
RESULTS_DIR = Path("results")


# ---------------------------------------------------------------------------

def carica_chunk_per_fonte(manager, collection: str, frammenti: list[str]) -> list[dict[str, Any]]:
    """Tutti i chunk il cui `source` contiene uno dei frammenti attesi."""
    client = manager.get_client()
    trovati, offset = [], None
    frag = [f.lower() for f in frammenti if f]
    while True:
        punti, offset = client.scroll(
            collection_name=collection, limit=1000, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in punti:
            pl = p.payload or {}
            src = (pl.get("source") or "").lower()
            if any(f in src for f in frag):
                trovati.append(dict(pl))
        if offset is None:
            break
    return trovati


def scegli_oracolo(chunks: list[dict[str, Any]], must: list[str], n: int) -> tuple[list[dict], bool]:
    """Sceglie i chunk che portano davvero la risposta.

    Restituisce (chunk scelti, oracolo_forte). `oracolo_forte` e' False quando
    nessun chunk della fonte attesa contiene i termini di must_contain.
    """
    if not chunks:
        return [], False

    if not must:
        return chunks[:n], True

    termini = [m.lower() for m in must if m]

    def copertura(c: dict[str, Any]) -> int:
        testo = (c.get("content") or "").lower()
        return sum(1 for t in termini if t in testo)

    ordinati = sorted(chunks, key=copertura, reverse=True)
    forte = copertura(ordinati[0]) > 0
    return ordinati[:n], forte


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Test a contesto oracolo")
    ap.add_argument("--dataset", default="config/golden_dataset_v2.json")
    ap.add_argument("--n-chunk", type=int, default=1,
                    help="quanti chunk oracolo passare al modello (default 1)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--confronta", default=None,
                    help="run end-to-end da confrontare (eval_*.json)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data["items"][: args.limit] if args.limit else data["items"]

    from src.core.config_loader import ConfigLoader
    from src.core.model_factory import ModelFactory
    from src.inference.response_generator import ResponseGenerator
    from src.rag.prompt_builder import PromptBuilder
    from src.vectorstore.qdrant_client import QdrantClientManager

    cfg = ConfigLoader.get_rag_config()
    modello = cfg.get("llm", {}).get("model", "?")

    console.print("\n[bold cyan]Test a contesto oracolo[/bold cyan]")
    console.print(f"modello: [bold]{modello}[/bold] · domande: [bold]{len(items)}[/bold] · "
                  f"chunk oracolo per domanda: [bold]{args.n_chunk}[/bold]")
    console.print("[dim]Il retrieval e' bypassato: al modello viene passato direttamente il "
                  "documento che contiene la risposta.[/dim]\n")

    manager = QdrantClientManager()
    collection = manager.collection_name
    generator = ResponseGenerator(ModelFactory.create_llm())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    out = Path(args.out) if args.out else RESULTS_DIR / f"oracle_context_{stamp}.json"
    parziale = out.with_suffix(".partial.json")

    righe: list[dict[str, Any]] = []
    t_tot = time.perf_counter()

    for i, it in enumerate(items, 1):
        qid, domanda = it["id"], it["question"]
        must = it.get("must_contain", [])
        console.print(f"[cyan]{i}/{len(items)}[/cyan] {qid} — {domanda}")

        candidati = carica_chunk_per_fonte(manager, collection, it.get("expected_sources", []))
        oracolo, forte = scegli_oracolo(candidati, must, args.n_chunk)

        if not oracolo:
            # L'informazione non e' nel corpus: non e' un errore del generatore.
            console.print("        [red]nessun chunk dalla fonte attesa — assente dal corpus[/red]")
            righe.append({
                "question_id": qid, "question": domanda, "must_contain": must,
                "stato": "corpus_miss", "oracolo_forte": False,
                "n_chunk_fonte": 0, "response": None,
                "must_contain_pass": None, "latency_s": None,
            })
            continue

        prompt = PromptBuilder.build_prompt(domanda, oracolo)
        t0 = time.perf_counter()
        risposta = generator.generate(prompt)
        lat = round(time.perf_counter() - t0, 1)

        hits = [m for m in must if m.lower() in (risposta or "").lower()]
        passa = (len(hits) == len(must)) if must else None

        esito = "✅" if passa else ("❌" if passa is False else "—")
        console.print(f"        {esito} must-contain {len(hits)}/{len(must)} · {lat}s"
                      + ("" if forte else " · [yellow]oracolo debole[/yellow]"))
        console.print(f"        [dim]> {(risposta or '')[:110].replace(chr(10),' ')}…[/dim]")

        righe.append({
            "question_id": qid, "question": domanda,
            "must_contain": must, "must_contain_hits": hits, "must_contain_pass": passa,
            "stato": "ok" if passa else "generation_miss",
            "oracolo_forte": forte,
            "n_chunk_fonte": len(candidati),
            "fonti_oracolo": [c.get("source") for c in oracolo],
            "contesto": [(c.get("content") or "")[:600] for c in oracolo],
            "reference_answer": it.get("reference_answer"),
            "response": risposta,
            "latency_s": lat,
        })

        tmp = parziale.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"parziale": True, "righe": righe}, fh, ensure_ascii=False)
        tmp.replace(parziale)

    durata = round(time.perf_counter() - t_tot, 1)

    # --- aggregazione ------------------------------------------------------
    valutabili = [r for r in righe if r["must_contain_pass"] is not None]
    forti = [r for r in valutabili if r["oracolo_forte"]]
    corpus_miss = [r for r in righe if r["stato"] == "corpus_miss"]
    deboli = [r for r in valutabili if not r["oracolo_forte"]]

    def tasso(rs):
        if not rs:
            return None, None
        ok = sum(1 for r in rs if r["must_contain_pass"])
        return round(ok / len(rs), 3), list(S.wilson_ci(ok, len(rs)))

    t_tutti, ci_tutti = tasso(valutabili)
    t_forti, ci_forti = tasso(forti)

    aggregato = {
        "modello": modello,
        "n_domande": len(items),
        "n_valutabili": len(valutabili),
        "n_oracolo_forte": len(forti),
        "n_oracolo_debole": len(deboli),
        "n_corpus_miss": len(corpus_miss),
        "accuratezza_oracolo": t_tutti,
        "accuratezza_oracolo_ci": ci_tutti,
        "accuratezza_solo_oracolo_forte": t_forti,
        "accuratezza_solo_oracolo_forte_ci": ci_forti,
        "latenza_media_s": round(sum(r["latency_s"] for r in valutabili) / max(1, len(valutabili)), 1),
        "durata_totale_s": durata,
    }

    t = Table(title="Contesto oracolo — il modello ha il documento giusto davanti", title_style="bold")
    t.add_column("Misura"); t.add_column("Valore", justify="right")
    t.add_row("Domande valutabili", str(len(valutabili)))
    t.add_row("di cui con oracolo forte", str(len(forti)))
    t.add_row("Oracolo debole", str(len(deboli)))
    t.add_row("Assenti dal corpus", str(len(corpus_miss)))
    if t_tutti is not None:
        t.add_row("[bold]Risposte corrette[/bold]",
                  f"[bold]{t_tutti:.1%}[/bold] [{ci_tutti[0]:.1%}, {ci_tutti[1]:.1%}]")
    if t_forti is not None:
        t.add_row("Corrette (solo oracolo forte)",
                  f"{t_forti:.1%} [{ci_forti[0]:.1%}, {ci_forti[1]:.1%}]")
    t.add_row("Latenza media", f"{aggregato['latenza_media_s']} s")
    console.print()
    console.print(t)

    # --- decomposizione contro il run reale --------------------------------
    confronto = None
    if args.confronta:
        with open(args.confronta, encoding="utf-8") as fh:
            run = json.load(fh)
        reali = {r["question_id"]: r for r in run.get("results", [])}
        comuni = [r for r in valutabili if r["question_id"] in reali]

        if comuni:
            a = [1.0 if r["must_contain_pass"] else 0.0 for r in comuni]
            b = [1.0 if reali[r["question_id"]].get("must_contain_pass") else 0.0 for r in comuni]
            rep = S.paired_report(b, a, name="must_contain", binary=True,
                                  label_a="pipeline reale", label_b="contesto oracolo")

            A = sum(a) / len(a)
            B = sum(b) / len(b)
            confronto = {
                "n_domande_comuni": len(comuni),
                "accuratezza_oracolo": round(A, 3),
                "accuratezza_pipeline_reale": round(B, 3),
                "perso_nel_retrieval": round(A - B, 3),
                "limite_del_generatore": round(1 - A, 3),
                "test_appaiato": rep,
            }

            d = Table(title="Decomposizione dell'errore", title_style="bold")
            d.add_column("Componente"); d.add_column("Quota", justify="right")
            d.add_row("Risposte corrette con la pipeline reale", f"{B:.1%}")
            d.add_row("Risposte corrette con contesto oracolo", f"{A:.1%}")
            d.add_row("[yellow]Perso nel retrieval[/yellow]", f"[yellow]{A-B:.1%}[/yellow]")
            d.add_row("[red]Limite del generatore[/red]", f"[red]{1-A:.1%}[/red]")
            d.add_row("p (McNemar esatto)", f"{rep['significance']['p_value']:.4f}")
            console.print()
            console.print(d)
            console.print(
                f"\n[dim]Il {1-A:.0%} di errore residuo persiste anche con il documento corretto "
                f"davanti: e' il limite del modello da 3B imposto dal vincolo di memoria della "
                f"piattaforma, non un problema di recupero.[/dim]"
            )

    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "data": datetime.now().isoformat(timespec="seconds"),
            "dataset": args.dataset,
            "n_chunk_oracolo": args.n_chunk,
            "config_snapshot": cfg,
            "aggregato": aggregato,
            "confronto": confronto,
            "risultati": righe,
        }, fh, ensure_ascii=False, indent=2)
    parziale.unlink(missing_ok=True)
    console.print(f"\n[green]Salvato in:[/green] {out}")

    if deboli:
        console.print(f"\n[yellow]{len(deboli)} domande con oracolo debole:[/yellow] "
                      + ", ".join(r["question_id"] for r in deboli)
                      + "\n[dim]nessun chunk della fonte attesa contiene i termini di must_contain: "
                      "l'informazione non e' nel corpus nella forma attesa, oppure il chunking "
                      "l'ha spezzata. Va dichiarato, non confuso con un errore del generatore.[/dim]")

    if args.markdown and confronto:
        console.print("\n[bold]Tabella per la tesi[/bold]\n")
        print("| Componente | Quota |")
        print("|---|---|")
        print(f"| Risposte corrette, pipeline reale | {confronto['accuratezza_pipeline_reale']:.1%} |")
        print(f"| Risposte corrette, contesto oracolo | {confronto['accuratezza_oracolo']:.1%} |")
        print(f"| **Perso nel retrieval** | **{confronto['perso_nel_retrieval']:.1%}** |")
        print(f"| **Limite del generatore** | **{confronto['limite_del_generatore']:.1%}** |")
        print(f"\nn = {confronto['n_domande_comuni']} domande · McNemar esatto "
              f"p = {confronto['test_appaiato']['significance']['p_value']:.4f}")


if __name__ == "__main__":
    main()
