#!/usr/bin/env python3
"""
Esporta un foglio di validazione umana dall'ultimo run di valutazione.

Genera results/validation_<data>.csv con le risposte del sistema e i punteggi
del judge LLM, piu' tre colonne vuote da compilare a mano (Excel/Numbers):

    faithfulness_umano, relevance_umano, correctness_umano, note

Una volta compilato, calcolare l'accordo con:
    python benchmarks/compute_judge_agreement.py --sheet results/validation_<data>.csv

Usage:
    python benchmarks/export_validation_sheet.py                     # ultimo run
    python benchmarks/export_validation_sheet.py --run results/2026-08-24/eval_FULL1.partial.json
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS_DIR = Path("results")


def find_latest_run() -> Path | None:
    candidates = sorted(RESULTS_DIR.glob("*/*.json"))
    runs = [p for p in candidates if p.name.startswith("eval_") and not p.name.endswith(".partial.json")]
    return runs[-1] if runs else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Esporta foglio di validazione umana")
    parser.add_argument("--run", default=None, help="Path del file eval_*.json (default: ultimo)")
    args = parser.parse_args()

    run_path = Path(args.run) if args.run else find_latest_run()
    if not run_path or not run_path.exists():
        print("Nessun run trovato. Specificare --run <path>")
        sys.exit(1)

    with open(run_path, encoding="utf-8") as fh:
        data = json.load(fh)

    out_path = RESULTS_DIR / f"validation_{datetime.now().strftime('%Y-%m-%d')}.csv"
    fields = [
        "question_id", "question", "response",
        "faithfulness_judge", "relevance_judge", "correctness_judge",
        "faithfulness_umano", "relevance_umano", "correctness_umano",
        "note",
    ]

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in data.get("rows", []):
            j = r.get("judgment") or {}
            sc = lambda k: (j.get(k) or {}).get("score", "")  # noqa: E731
            writer.writerow({
                "question_id": r.get("question_id"),
                "question": r.get("question"),
                "response": (r.get("response") or "").replace("\n", " "),
                "faithfulness_judge": sc("faithfulness"),
                "relevance_judge": sc("answer_relevance"),
                "correctness_judge": sc("correctness"),
                "faithfulness_umano": "",
                "relevance_umano": "",
                "correctness_umano": "",
                "note": "",
            })

    print(f"Foglio di validazione creato: {out_path}")
    print("Istruzioni:")
    print("  1. Apri il CSV in Excel/Numbers")
    print("  2. Leggi ogni risposta e dai i TUOI punteggi (0-5) nelle colonne *_umano")
    print("     - faithfulness: la risposta e' supportata dai documenti? (vedi run JSON per il contesto)")
    print("     - relevance: risponde alla domanda?")
    print("     - correctness: e' coerente con la reference answer? (nel run JSON)")
    print("  3. Salva ed esegui: python benchmarks/compute_judge_agreement.py --sheet " + str(out_path))


if __name__ == "__main__":
    main()
