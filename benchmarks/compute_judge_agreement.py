#!/usr/bin/env python3
"""
Calcola l'accordo tra giudice umano e LLM-judge dal foglio di validazione.

Produce, per ciascuna metrica (faithfulness, relevance, correctness):
  - MAE:  errore medio assoluto |umano - judge| (piu' basso = migliore)
  - Exact match %: quante volte il voto coincide esattamente
  - Within-1 %: quante volte la differenza e' al massimo 1
  - Pearson r: correlazione lineare tra i due insiemi di voti

Salva i risultati in results/judge_agreement_<data>.json per la tesi.

Usage:
    python benchmarks/compute_judge_agreement.py --sheet results/validation_2026-08-24.csv
"""
import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

METRICS = [
    ("faithfulness", "faithfulness_umano", "faithfulness_judge"),
    ("relevance", "relevance_umano", "relevance_judge"),
    ("correctness", "correctness_umano", "correctness_judge"),
]


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def main() -> None:
    parser = argparse.ArgumentParser(description="Accordo umano vs LLM-judge")
    parser.add_argument("--sheet", required=True, help="CSV compilato con i voti umani")
    args = parser.parse_args()

    with open(args.sheet, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    report = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "sheet": args.sheet,
        "n_items": len(rows),
        "agreement": {},
    }

    print(f"\nAccordo umano vs LLM-judge ({len(rows)} risposte valutate)\n")

    header = f"{'Metrica':<14}{'MAE':>6}{'Exact':>8}{'Within1':>9}{'Pearson r':>11}"
    print(header)
    print("-" * len(header))

    for name, human_col, judge_col in METRICS:
        pairs = []
        for r in rows:
            h, j = (r.get(human_col, "").strip(), r.get(judge_col, "").strip())
            if h and j and h.replace(".", "", 1).isdigit() and j.replace(".", "", 1).isdigit():
                pairs.append((float(h), float(j)))

        if not pairs:
            print(f"{name:<14}{'--':>6}{'--':>8}{'--':>9}{'--':>11}   (nessun voto compilato)")
            continue

        hs, js = [p[0] for p in pairs], [p[1] for p in pairs]
        diffs = [abs(h - j) for h, j in pairs]
        mae = sum(diffs) / len(diffs)
        exact = sum(1 for d in diffs if d == 0) / len(pairs)
        within1 = sum(1 for d in diffs if d <= 1) / len(pairs)
        r = pearson(hs, js)

        print(f"{name:<14}{mae:>6.2f}{exact:>7.0%}{within1:>8.0%}{r:>11.2f}")

        report["agreement"][name] = {
            "n": len(pairs),
            "mae": round(mae, 3),
            "exact_match_rate": round(exact, 3),
            "within_1_rate": round(within1, 3),
            "pearson_r": round(r, 3),
        }

    out_path = Path("results") / f"judge_agreement_{datetime.now().strftime('%Y-%m-%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"\nReport salvato in: {out_path}")
    print("Interpretazione: MAE<=1 e within-1 >=80% indicano un judge affidabile;")
    print("riporta questa tabella nel capitolo sperimentale come validazione del metodo.")


if __name__ == "__main__":
    main()
