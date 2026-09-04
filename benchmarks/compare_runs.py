#!/usr/bin/env python3
"""
Confronto statistico fra due run di valutazione (ablation study).

E' lo strumento del capitolo sperimentale: due configurazioni valutate sulle
STESSE domande, confrontate con test appaiati.

Perche' appaiati
----------------
Le due configurazioni rispondono allo stesso golden dataset, quindi ogni
domanda compare in entrambi i run. Le osservazioni sono accoppiate, e i test
appaiati eliminano la variabilita' dovuta al fatto che certe domande sono
intrinsecamente piu' difficili. Con n = 30 la differenza di potenza
statistica rispetto ai test per campioni indipendenti e' sostanziale.

Il confronto e' ristretto alle domande presenti in ENTRAMBI i run: se un run
e' parziale, le domande mancanti sono escluse da entrambi i lati e il numero
effettivo e' riportato.

Cosa viene riportato, per ogni metrica
--------------------------------------
  - media con IC 95% per ciascuna configurazione
  - differenza media con IC 95% bootstrap sulle differenze appaiate
  - p-value (Wilcoxon per gli ordinali, McNemar esatto per i binari)
  - dimensione dell'effetto (delta di Cliff)

Un p-value da solo non basta: dice se la differenza sia distinguibile dal
rumore, non se sia grande abbastanza da contare. Vanno riportati entrambi.

Usage:
    python benchmarks/compare_runs.py --a results/.../eval_A.json \\
                                      --b results/.../eval_B.json
    python benchmarks/compare_runs.py --a ... --b ... --label-a "top_k=10" \\
                                      --label-b "top_k=25" --markdown
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

from benchmarks import stats as S

console = Console()

# (chiave, dove leggerla, e' binaria?, etichetta)
COMPARED_METRICS: list[tuple[str, str, bool, str]] = [
    ("hit_at_3", "retrieval_context", True, "Hit@3 (contesto)"),
    ("hit_at_5", "retrieval_context", True, "Hit@5 (contesto)"),
    ("mrr", "retrieval_context", False, "MRR (contesto)"),
    ("recall_at_5", "retrieval_context", False, "Recall@5 (contesto)"),
    ("ndcg_at_5", "retrieval_context", False, "nDCG@5 (contesto)"),
    ("hit_at_5", "retrieval", True, "Hit@5 (candidati)"),
    ("hit_at_10", "retrieval", True, "Hit@10 (candidati)"),
    ("mrr", "retrieval", False, "MRR (candidati)"),
]


def load_run(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def index_by_question(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["question_id"]: r for r in run.get("results", []) if r.get("question_id")}


def paired_values(
    rows_a: dict[str, dict[str, Any]],
    rows_b: dict[str, dict[str, Any]],
    qids: list[str],
    stage: str,
    key: str,
) -> tuple[list[float], list[float]]:
    xs, ys = [], []
    for qid in qids:
        a_stage = rows_a[qid].get(stage) or {}
        b_stage = rows_b[qid].get(stage) or {}
        xs.append(float(a_stage.get(key, 0) or 0))
        ys.append(float(b_stage.get(key, 0) or 0))
    return xs, ys


def judge_values(rows: dict[str, dict[str, Any]], qids: list[str], key: str) -> list[float | None]:
    out: list[float | None] = []
    for qid in qids:
        j = rows[qid].get("judgment") or {}
        score = (j.get(key) or {}).get("score")
        out.append(float(score) if score is not None and score >= 0 else None)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Confronto appaiato fra due run")
    parser.add_argument("--a", required=True, help="Run di riferimento (baseline)")
    parser.add_argument("--b", required=True, help="Run da confrontare")
    parser.add_argument("--label-a", default=None)
    parser.add_argument("--label-b", default=None)
    parser.add_argument("--markdown", action="store_true", help="Stampa in Markdown, da incollare in tesi")
    parser.add_argument("--out", default=None, help="Salva il confronto in JSON")
    args = parser.parse_args()

    run_a, run_b = load_run(args.a), load_run(args.b)
    label_a = args.label_a or run_a.get("run_id", "A")
    label_b = args.label_b or run_b.get("run_id", "B")

    rows_a, rows_b = index_by_question(run_a), index_by_question(run_b)
    qids = sorted(set(rows_a) & set(rows_b))

    if len(qids) < 2:
        console.print("[red]Meno di 2 domande in comune fra i due run: confronto impossibile.[/red]")
        sys.exit(1)

    only_a, only_b = sorted(set(rows_a) - set(rows_b)), sorted(set(rows_b) - set(rows_a))
    if only_a or only_b:
        console.print(
            f"[yellow]Domande non comuni escluse — solo in A: {len(only_a)}, solo in B: {len(only_b)}[/yellow]"
        )

    console.print(f"\n[bold cyan]Confronto appaiato[/bold cyan]  {label_a}  vs  {label_b}")
    console.print(f"Domande in comune: [bold]{len(qids)}[/bold]\n")

    # Avviso sulle differenze di configurazione: cosa e' effettivamente cambiato.
    cfg_a, cfg_b = run_a.get("config_snapshot") or {}, run_b.get("config_snapshot") or {}
    diffs = _config_diff(cfg_a, cfg_b)
    if diffs:
        console.print("[bold]Differenze di configurazione[/bold]")
        for path, va, vb in diffs:
            console.print(f"  {path}: [yellow]{va}[/yellow] -> [green]{vb}[/green]")
        console.print()
    else:
        console.print("[yellow]Attenzione: le due configurazioni risultano identiche. "
                      "Le differenze osservate sarebbero solo rumore.[/yellow]\n")

    report: dict[str, Any] = {
        "run_a": {"file": args.a, "run_id": run_a.get("run_id"), "label": label_a},
        "run_b": {"file": args.b, "run_id": run_b.get("run_id"), "label": label_b},
        "n_paired": len(qids),
        "question_ids": qids,
        "config_diff": [{"path": p, "a": a, "b": b} for p, a, b in diffs],
        "metrics": {},
        "stats_environment": S.describe_environment(),
    }

    table = Table(title=f"Metriche di retrieval (n={len(qids)}, IC 95%)", title_style="bold")
    table.add_column("Metrica")
    table.add_column(label_a, justify="right")
    table.add_column(label_b, justify="right")
    table.add_column("Diff.", justify="right")
    table.add_column("IC 95% diff.", justify="right")
    table.add_column("p", justify="right")
    table.add_column("Effetto", justify="right")

    for key, stage, binary, label in COMPARED_METRICS:
        xs, ys = paired_values(rows_a, rows_b, qids, stage, key)
        if not any(xs) and not any(ys):
            continue
        rep = S.paired_report(xs, ys, name=label, binary=binary, label_a="a", label_b="b")
        report["metrics"][label] = rep
        _add_row(table, label, rep, pct=binary)

    console.print(table)

    # --- punteggi del judge, solo se validato in entrambi i run ------------
    validated = run_a.get("judge_validated") and run_b.get("judge_validated")
    judge_keys = [("faithfulness", "Fedelta'"), ("answer_relevance", "Pertinenza"), ("correctness", "Correttezza")]
    has_judge = run_a.get("judge_enabled") and run_b.get("judge_enabled")

    if has_judge:
        jt = Table(title="Punteggi del judge (0-5)" + ("" if validated else "  —  NON VALIDATI"),
                   title_style="bold" if validated else "bold yellow")
        jt.add_column("Metrica")
        jt.add_column(label_a, justify="right")
        jt.add_column(label_b, justify="right")
        jt.add_column("Diff.", justify="right")
        jt.add_column("p", justify="right")
        jt.add_column("Effetto", justify="right")

        for key, label in judge_keys:
            va, vb = judge_values(rows_a, qids, key), judge_values(rows_b, qids, key)
            pairs = [(x, y) for x, y in zip(va, vb) if x is not None and y is not None]
            if len(pairs) < 2:
                continue
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            rep = S.paired_report(xs, ys, name=label, binary=False, label_a="a", label_b="b")
            rep["judge_validated"] = bool(validated)
            report["metrics"][f"judge_{key}"] = rep
            jt.add_row(
                label,
                S.format_ci(rep["a"]),
                S.format_ci(rep["b"]),
                f"{rep['mean_difference']:+.3f}",
                f"{rep['significance']['p_value']:.4f}",
                rep["effect_size"]["magnitude"],
            )
        console.print(jt)

        if not validated:
            console.print(
                "\n[yellow]Il judge non e' validato in almeno uno dei due run: "
                "questi punteggi non sono riportabili come risultati.[/yellow]"
            )

    # --- must_contain: deterministico, sempre utilizzabile -----------------
    mc_a = [1.0 if rows_a[q].get("must_contain_pass") else 0.0 for q in qids]
    mc_b = [1.0 if rows_b[q].get("must_contain_pass") else 0.0 for q in qids]
    if any(mc_a) or any(mc_b):
        rep = S.paired_report(mc_a, mc_b, name="must_contain", binary=True, label_a="a", label_b="b")
        report["metrics"]["must_contain"] = rep
        mt = Table(title="Must-contain (check deterministico)", title_style="bold")
        mt.add_column("Metrica")
        mt.add_column(label_a, justify="right")
        mt.add_column(label_b, justify="right")
        mt.add_column("Diff.", justify="right")
        mt.add_column("p", justify="right")
        _add_row(mt, "Pass rate", rep, pct=True, short=True)
        console.print(mt)

    # --- latenza ----------------------------------------------------------
    lat_a = [float(rows_a[q].get("latency_s", 0) or 0) for q in qids]
    lat_b = [float(rows_b[q].get("latency_s", 0) or 0) for q in qids]
    if any(lat_a) and any(lat_b):
        rep = S.paired_report(lat_a, lat_b, name="latency_s", binary=False, label_a="a", label_b="b")
        report["metrics"]["latency_s"] = rep
        console.print(
            f"\n[bold]Latenza (s)[/bold]  {label_a}: {S.format_ci(rep['a'])}   "
            f"{label_b}: {S.format_ci(rep['b'])}   "
            f"diff {rep['mean_difference']:+.1f}s  p={rep['significance']['p_value']:.4f}"
        )

    if args.markdown:
        console.print("\n" + _markdown(report, label_a, label_b))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        console.print(f"\n[green]Confronto salvato in:[/green] {out_path}")


def _add_row(table: Table, label: str, rep: dict[str, Any], pct: bool = False, short: bool = False) -> None:
    ci = rep.get("difference_ci")
    cells = [label, S.format_ci(rep["a"], pct=pct), S.format_ci(rep["b"], pct=pct),
             f"{rep['mean_difference']:+.3f}"]
    if not short:
        cells.append(f"[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "—")
    cells.append(f"{rep['significance']['p_value']:.4f}")
    if not short:
        cells.append(rep["effect_size"]["magnitude"])
    table.add_row(*cells)


def _config_diff(a: dict[str, Any], b: dict[str, Any], prefix: str = "") -> list[tuple[str, Any, Any]]:
    """Differenze fra due config_snapshot, ricorsivo sui dizionari annidati."""
    out: list[tuple[str, Any, Any]] = []
    for key in sorted(set(a) | set(b)):
        path = f"{prefix}{key}"
        va, vb = a.get(key), b.get(key)
        if isinstance(va, dict) and isinstance(vb, dict):
            out.extend(_config_diff(va, vb, prefix=f"{path}."))
        elif va != vb:
            out.append((path, va, vb))
    return out


def _markdown(report: dict[str, Any], label_a: str, label_b: str) -> str:
    lines = [
        f"### Confronto: {label_a} vs {label_b}",
        "",
        f"Domande appaiate: **{report['n_paired']}** · IC 95% · "
        f"bootstrap {report['stats_environment']['bootstrap_resamples']} ricampionamenti "
        f"(seme {report['stats_environment']['seed']})",
        "",
        f"| Metrica | {label_a} | {label_b} | Diff. | p | Effetto |",
        "|---|---|---|---|---|---|",
    ]
    for label, rep in report["metrics"].items():
        pct = "Hit@" in label or label == "must_contain"
        lines.append(
            f"| {label} | {S.format_ci(rep['a'], pct=pct)} | {S.format_ci(rep['b'], pct=pct)} | "
            f"{rep['mean_difference']:+.3f} | {rep['significance']['p_value']:.4f} | "
            f"{rep['effect_size']['magnitude']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
