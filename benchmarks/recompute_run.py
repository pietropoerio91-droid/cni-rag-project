#!/usr/bin/env python3
"""
Ricalcola le metriche di un run gia' eseguito, con le definizioni corrette.

A cosa serve
------------
I run prodotti prima della correzione delle metriche contengono valori
sbagliati (recall non troncato a k, matching asimmetrico, calcolo sui soli
candidati pre-reranking). Le RISPOSTE e le liste di documenti salvate in quei
run sono pero' valide: non serve rieseguire la valutazione — che costa ore —
per ottenere i numeri giusti.

Questo script rilegge un run, ricalcola tutto con `metrics.py` e `stats.py`,
e salva un nuovo file accanto all'originale con suffisso `.recomputed.json`.
L'originale non viene toccato.

Limite dichiarato: i run vecchi salvano solo gli URL dei documenti
(`retrieved_sources`, `reranked_sources`), non i loro titoli. La rilevanza
viene quindi valutata sul solo campo `source`. Per le fonti attese del golden
dataset — che sono frammenti di URL — la differenza e' nulla nella pratica,
ma va detta.

I punteggi del judge NON vengono ricalcolati: sono quelli originali, e
restano non validati.

Usage:
    python benchmarks/recompute_run.py --run results/2026-08-24/eval_12-58-40.json
    python benchmarks/recompute_run.py --run <file> --quiet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from benchmarks import metrics as M
from benchmarks import stats as S

console = Console()
K_VALUES = (1, 3, 5, 10)


def docs_from_sources(sources: list[str] | None) -> list[dict[str, Any]]:
    return [{"source": s, "title": ""} for s in (sources or [])]


def recompute(run: dict[str, Any]) -> dict[str, Any]:
    rows = run.get("results", [])

    for row in rows:
        expected = row.get("expected_sources", [])
        pre = docs_from_sources(row.get("retrieved_sources"))
        post = docs_from_sources(row.get("reranked_sources"))

        stages = M.evaluate_stages(pre, post, expected, K_VALUES)
        row["retrieval_legacy"] = row.get("retrieval")   # conserva i vecchi valori
        row["retrieval"] = stages["retrieved"]
        row["retrieval_context"] = stages["context"]
        row["reranker_gain"] = M.reranker_gain(stages, k=5)

    def stage_summary(field: str) -> dict[str, Any]:
        per_q = [r[field] for r in rows if r.get(field)]
        if not per_q:
            return {}
        keys = ["mrr"] + [f"{m}_at_{k}" for k in K_VALUES for m in ("hit", "recall", "precision", "ndcg")]
        return {
            "point": M.aggregate_rankings(per_q, K_VALUES),
            "ci": {
                key: S.summarize_metric(M.column(per_q, key), key, binary=key.startswith("hit"))
                for key in keys
            },
        }

    pre_q = [r["retrieval"] for r in rows]
    post_q = [r["retrieval_context"] for r in rows]

    reranker_effect = {}
    if len(pre_q) >= 2:
        for key, binary in [("hit_at_5", True), ("mrr", False),
                            ("recall_at_5", False), ("ndcg_at_5", False)]:
            reranker_effect[key] = S.paired_report(
                M.column(pre_q, key), M.column(post_q, key),
                name=key, binary=binary, label_a="pre_rerank", label_b="post_rerank",
            )

    agg = run.setdefault("aggregate", {})
    agg["aggregate_legacy"] = {k: v for k, v in agg.items() if k != "aggregate_legacy"}
    agg["retrieval_stages"] = {"retrieved": stage_summary("retrieval"), "context": stage_summary("retrieval_context")}
    agg["reranker_effect"] = reranker_effect
    agg["retrieval"] = agg["retrieval_stages"]["retrieved"].get("point", {})

    n = len(rows)
    if n:
        fb = sum(1 for r in rows if r.get("fallback_triggered"))
        agg["fallback_rate"] = round(fb / n, 3)
        agg["fallback_rate_ci"] = list(S.wilson_ci(fb, n))
        mc_done = [r for r in rows if r.get("must_contain_pass") is not None]
        if mc_done:
            agg.setdefault("generation", {})["must_contain_ci"] = list(
                S.wilson_ci(sum(1 for r in mc_done if r["must_contain_pass"]), len(mc_done))
            )
        gen_ci = {}
        for key in ("faithfulness", "answer_relevance", "correctness"):
            vals = [r["judgment"][key]["score"] for r in rows
                    if r.get("judgment") and (r["judgment"].get(key) or {}).get("score") is not None
                    and r["judgment"][key]["score"] >= 0]
            if vals:
                gen_ci[key] = S.summarize_metric(vals, key)
        if gen_ci:
            agg.setdefault("generation", {})["ci"] = gen_ci
        lat = [r.get("latency_s", 0) for r in rows]
        if len(lat) >= 2:
            agg["latency_ci"] = list(S.bootstrap_ci(lat))

    run["judge_validated"] = run.get("judge_validated", False)
    run["judge_model"] = run.get("judge_model") or (run.get("config_snapshot", {}).get("llm", {}) or {}).get("model")
    run["stats_environment"] = S.describe_environment()
    run["k_values"] = list(K_VALUES)
    run["recomputed"] = {
        "note": "Metriche ricalcolate con benchmarks/metrics.py. Rilevanza valutata sul solo campo source (i run vecchi non salvano i titoli). Punteggi del judge invariati.",
        "legacy_preserved_in": ["results[].retrieval_legacy", "aggregate.aggregate_legacy"],
    }
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description="Ricalcola le metriche di un run esistente")
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    path = Path(args.run)
    with open(path, encoding="utf-8") as fh:
        run = json.load(fh)

    legacy = dict(run.get("aggregate", {}))
    run = recompute(run)

    out_path = Path(args.out) if args.out else path.with_suffix(".recomputed.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(run, fh, ensure_ascii=False, indent=2)

    if not args.quiet:
        agg = run["aggregate"]
        stages = agg["retrieval_stages"]

        t = Table(title=f"Metriche ricalcolate — {run.get('run_id')} (n={agg.get('total_questions')})",
                  title_style="bold")
        t.add_column("Metrica")
        t.add_column("Vecchio valore", justify="right")
        t.add_column("Pre-rerank (IC 95%)", justify="right")
        t.add_column("Post-rerank (IC 95%)", justify="right")

        legacy_ret = legacy.get("retrieval", {})
        for key in ("hit_at_3", "hit_at_5", "hit_at_10", "mrr", "recall_at_5", "ndcg_at_5"):
            old = legacy_ret.get(key)
            if key == "recall_at_5" and old is None:
                old = legacy_ret.get("recall")
            pre = (stages["retrieved"].get("ci") or {}).get(key)
            post = (stages["context"].get("ci") or {}).get(key)
            pct = key.startswith("hit")
            t.add_row(
                key,
                f"{old:.3f}" if isinstance(old, (int, float)) else "—",
                S.format_ci(pre, pct=pct) if pre else "—",
                S.format_ci(post, pct=pct) if post else "—",
            )
        console.print(t)

        if agg.get("reranker_effect"):
            e = Table(title="Effetto del reranker (appaiato)", title_style="bold")
            e.add_column("Metrica"); e.add_column("Diff.", justify="right")
            e.add_column("p", justify="right"); e.add_column("Effetto", justify="right")
            for key, rep in agg["reranker_effect"].items():
                e.add_row(key, f"{rep['mean_difference']:+.3f}",
                          f"{rep['significance']['p_value']:.4f}", rep["effect_size"]["magnitude"])
            console.print(e)

        console.print(f"\n[green]Salvato in:[/green] {out_path}")
        console.print("[dim]L'originale non e' stato modificato.[/dim]")


if __name__ == "__main__":
    main()
