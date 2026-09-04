#!/usr/bin/env python3
"""
Genera il report aggregato in Markdown di un run di valutazione end-to-end.

Legge il JSON di un run (completo o parziale) prodotto da run_evaluation.py
e produce una tabella per domanda + statistiche aggregate, salvandole in
results/report_<run_id>.md e stampandole a schermo.

Usage:
    python benchmarks/make_report.py --run results/2026-08-24/eval_10-41-10.json
    python benchmarks/make_report.py --run results/2026-08-24/eval_FULL1.partial.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def fmt(v, nd=2):
    return "–" if v is None else f"{v:.{nd}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Markdown di un run di valutazione")
    parser.add_argument("--run", required=True, help="Percorso del JSON del run")
    args = parser.parse_args()

    data = json.loads(Path(args.run).read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    if not rows:
        sys.exit("Nessuna riga nel file di run specificato.")

    lines = []
    n = len(rows)
    lines.append(f"# Report valutazione end-to-end — run `{data.get('run_id', 'n/d')}`")
    lines.append(f"\nGenerato: {datetime.now().isoformat(timespec='seconds')} — item completati: **{n}**\n")

    lines.append("| ID | Categoria | Rank | H@3 | H@5 | MRR | Recall | Fedeltà | Pertinenza | Correttezza | Must | Fallback | Lat. (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        j = r.get("judgment") or {}
        sc = lambda k: str((j.get(k) or {}).get("score", "–"))
        ret = r.get("retrieval") or {}
        rank = ret.get("first_relevant_rank")
        lines.append(
            f"| {r['question_id']} | {r.get('category','–')} "
            f"| {rank if rank is not None else '>25'} "
            f"| {ret.get('hit_at_3','-')} | {ret.get('hit_at_5','-')} "
            f"| {fmt(ret.get('mrr'))} | {fmt(ret.get('recall'))} "
            f"| {sc('faithfulness')} | {sc('answer_relevance')} | {sc('correctness')} "
            f"| {'✅' if r.get('must_contain_pass') else '❌'} "
            f"| {'sì' if r.get('fallback_triggered') else 'no'} "
            f"| {r.get('latency_s', 0):.0f} |"
        )

    def avg(key, sub=None):
        vals = []
        for r in rows:
            v = (r.get(key) or {}).get(sub) if sub else r.get(key)
            if isinstance(v, dict):
                v = v.get("score")
            if isinstance(v, (int, float)):
                vals.append(v)
        return sum(vals) / len(vals) if vals else None

    def rate(pred):
        return 100 * sum(1 for r in rows if pred(r)) / n

    agg = {
        "n_items": n,
        "hit_at_3_pct": rate(lambda r: (r.get("retrieval") or {}).get("hit_at_3") == 1),
        "hit_at_5_pct": rate(lambda r: (r.get("retrieval") or {}).get("hit_at_5") == 1),
        "hit_at_10_pct": rate(lambda r: (r.get("retrieval") or {}).get("hit_at_10") == 1),
        "mrr_mean": avg("retrieval", "mrr"),
        "recall_mean": avg("retrieval", "recall"),
        "must_contain_pct": rate(lambda r: r.get("must_contain_pass")),
        "fallback_pct": rate(lambda r: r.get("fallback_triggered")),
        "faithfulness_mean": avg("judgment", "faithfulness"),
        "answer_relevance_mean": avg("judgment", "answer_relevance"),
        "correctness_mean": avg("judgment", "correctness"),
        "latency_s_mean": avg("latency_s"),
    }

    lines.append("\n## Aggregate\n")
    lines.append("| Metrica | Valore |")
    lines.append("|---|---|")
    lines.append(f"| Hit@3 | {agg['hit_at_3_pct']:.0f}% |")
    lines.append(f"| Hit@5 | {agg['hit_at_5_pct']:.0f}% |")
    lines.append(f"| Hit@10 | {agg['hit_at_10_pct']:.0f}% |")
    lines.append(f"| MRR medio | {fmt(agg['mrr_mean'])} |")
    lines.append(f"| Recall medio | {fmt(agg['recall_mean'])} |")
    lines.append(f"| Must-contain superato | {agg['must_contain_pct']:.0f}% |")
    lines.append(f"| Fallback attivato | {agg['fallback_pct']:.0f}% |")
    lines.append(f"| Fedeltà media (0-5) | {fmt(agg['faithfulness_mean'])} |")
    lines.append(f"| Pertinenza media (0-5) | {fmt(agg['answer_relevance_mean'])} |")
    lines.append(f"| Correttezza media (0-5) | {fmt(agg['correctness_mean'])} |")
    lines.append(f"| Latenza media (s) | {agg['latency_s_mean']:.0f} |")

    report = "\n".join(lines) + "\n"
    print(report)

    out = Path(args.run).parent / f"report_{data.get('run_id','run')}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[salvato] {out}")


if __name__ == "__main__":
    main()
