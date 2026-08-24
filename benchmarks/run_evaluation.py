#!/usr/bin/env python3
"""
Valutazione end-to-end del sistema RAG CNI (retrieval + generazione).

A differenza di run_benchmark.py (che valuta solo il retrieval con keyword
matching), questo harness valuta la qualita' della risposta generata tramite
LLM-as-judge (qwen2.5:3b locale) e calcola le metriche di retrieval contro le
fonti attese del golden dataset.

Metriche di retrieval:
  - hit_at_k:    fraction di domande con almeno una fonte attesa nei top-k
  - mrr:         Mean Reciprocal Rank della prima fonte attesa (su retrieved)
  - recall_at_k: fraction di fonti attese trovate nei top-k

Metriche qualitative (LLM-as-judge, scala 0-5):
  - faithfulness:      la risposta e' coerente con i documenti recuperati?
  - answer_relevance:  la risposta risponde effettivamente alla domanda?
  - correctness:       la risposta e' coerente con la reference answer?

Persistenza per giorno:
  results/YYYY-MM-DD/eval_HH-MM-SS.json   dettaglio completo del run
  results/history.csv                     una riga per (run, domanda) — append
  results/index.json                      indice dei run

Usage:
    python benchmarks/run_evaluation.py
    python benchmarks/run_evaluation.py --limit 3
    python benchmarks/run_evaluation.py --no-judge          # solo retrieval
    python benchmarks/run_evaluation.py --dataset config/golden_dataset.json
"""
import argparse
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from rich.console import Console
from rich.table import Table

from src.core.config_loader import ConfigLoader
from src.inference.llm_client import LLMClient

console = Console()
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
API_BASE = "http://localhost:8000/api/v1"
JUDGE_FAITHFULNESS = """Sei un valutatore rigoroso di sistemi RAG.
Domanda dell'utente: {question}
Risposta generata dal sistema: {answer}
Documenti recuperati (contesto): {context}

La risposta generata e' interamente supportata dai documenti? Ignora se la risposta e' utile: valuta SOLO se le affermazioni sono presenti nel contesto (niente allucinazioni).
Rispondi ESATTAMENTE in questo formato:
SCORE: <numero da 0 a 5>
MOTIVO: <una frase>"""

JUDGE_RELEVANCE = """Sei un valutatore rigoroso di sistemi RAG.
Domanda dell'utente: {question}
Risposta generata dal sistema: {answer}

La risposta risponde in modo diretto e completo alla domanda dell'utente?
Rispondi ESATTAMENTE in questo formato:
SCORE: <numero da 0 a 5>
MOTIVO: <una frase>"""

JUDGE_CORRECTNESS = """Sei un valutatore rigoroso di sistemi RAG.
Domanda: {question}
Risposta di riferimento (verita' nota): {reference}
Risposta generata dal sistema: {answer}

Quanto la risposta generata e' coerente con la verita' nota? Valuta correttezza fattuale, non completezza verbale.
Rispondi ESATTAMENTE in questo formato:
SCORE: <numero da 0 a 5>
MOTIVO: <una frase>"""


def parse_judge_score(text: str) -> tuple[int, str]:
    """Estrae lo score 0-5 e il motivo dalla risposta del judge."""
    match = re.search(r"score\s*[:\-]?\s*([0-5])", text, re.IGNORECASE)
    score = int(match.group(1)) if match else -1
    reason_match = re.search(r"motivo\s*[:\-]?\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    reason = reason_match.group(1).strip().split("\n")[0][:300] if reason_match else ""
    return score, reason


def doc_matches_source(doc: dict[str, Any], expected_sources: list[str]) -> bool:
    source = (doc.get("source") or "").lower()
    title = (doc.get("title") or "").lower()
    return any(frag.lower() in source or frag.lower() in title for frag in expected_sources)


def retrieval_metrics(docs: list[dict[str, Any]], expected_sources: list[str], k_values=(3, 5, 10)) -> dict[str, Any]:
    hits = {k: 0 for k in k_values}
    relevant_ranks = [i + 1 for i, d in enumerate(docs) if doc_matches_source(d, expected_sources)]

    first_rank = relevant_ranks[0] if relevant_ranks else None
    for k in k_values:
        hits[k] = int(first_rank is not None and first_rank <= k)

    n_expected = len(expected_sources)
    found_sources = set()
    for i, d in enumerate(docs):
        if doc_matches_source(d, expected_sources):
            for frag in expected_sources:
                if frag.lower() in (d.get("source") or "").lower():
                    found_sources.add(frag)
    recall = len(found_sources) / n_expected if n_expected else 0.0

    return {
        "first_relevant_rank": first_rank,
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        **{f"hit_at_{k}": v for k, v in hits.items()},
        "recall": recall,
        "n_docs": len(docs),
    }


class LLMJudge:
    def __init__(self):
        self.client = LLMClient()

    def _ask(self, template: str, **kwargs) -> tuple[int, str]:
        prompt = template.format(**kwargs)
        try:
            raw = self.client.invoke([{"role": "user", "content": prompt}])
            return parse_judge_score(raw)
        except Exception as exc:
            logger.warning(f"Judge failed: {exc}")
            return -1, f"judge_error: {exc}"

    def evaluate(self, question: str, answer: str, context: str, reference: str) -> dict[str, Any]:
        f_score, f_reason = self._ask(
            JUDGE_FAITHFULNESS, question=question, answer=answer, context=context[:4000]
        )
        r_score, r_reason = self._ask(JUDGE_RELEVANCE, question=question, answer=answer)
        c_score, c_reason = self._ask(
            JUDGE_CORRECTNESS, question=question, reference=reference, answer=answer
        )
        return {
            "faithfulness": {"score": f_score, "reason": f_reason},
            "answer_relevance": {"score": r_score, "reason": r_reason},
            "correctness": {"score": c_score, "reason": c_reason},
        }


def load_dataset(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["items"]


def save_run(run_data: dict[str, Any], items_rows: list[dict[str, Any]]) -> Path:
    now = datetime.now()
    day_dir = RESULTS_DIR / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    stamp = now.strftime("%H-%M-%S")
    run_file = day_dir / f"eval_{stamp}.json"
    with open(run_file, "w", encoding="utf-8") as fh:
        json.dump(run_data, fh, ensure_ascii=False, indent=2)

    history_path = RESULTS_DIR / "history.csv"
    fieldnames = [
        "run_date", "run_id", "dataset_version", "question_id", "question", "category",
        "fallback_triggered", "first_relevant_rank", "mrr",
        "faithfulness", "answer_relevance", "correctness",
        "latency_s", "response_preview",
    ]
    exists = history_path.exists()
    with open(history_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(items_rows)

    summary_path = RESULTS_DIR / "summary.csv"
    summary_fields = [
        "run_date", "run_id", "total_questions", "fallback_rate",
        "hit_at_3", "hit_at_5", "hit_at_10", "mrr", "recall",
        "avg_faithfulness", "avg_answer_relevance", "avg_correctness",
        "pass_rate_correctness_ge4", "avg_latency_s", "duration_s",
    ]
    s = run_data["aggregate"]
    row = {
        "run_date": run_data["run_date"],
        "run_id": run_data["run_id"],
        "total_questions": s["total_questions"],
        "fallback_rate": s["fallback_rate"],
        "hit_at_3": s["retrieval"]["hit_at_3"],
        "hit_at_5": s["retrieval"]["hit_at_5"],
        "hit_at_10": s["retrieval"]["hit_at_10"],
        "mrr": s["retrieval"]["mrr"],
        "recall": s["retrieval"]["recall"],
        "avg_faithfulness": s["generation"].get("avg_faithfulness"),
        "avg_answer_relevance": s["generation"].get("avg_answer_relevance"),
        "avg_correctness": s["generation"].get("avg_correctness"),
        "pass_rate_correctness_ge4": s["generation"].get("pass_rate_correctness_ge4"),
        "avg_latency_s": s.get("avg_latency_s"),
        "duration_s": run_data.get("duration_s"),
    }
    exists = summary_path.exists()
    with open(summary_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)

    index_path = RESULTS_DIR / "index.json"
    index: list[dict[str, Any]] = []
    if index_path.exists():
        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)
    index.append({
        "run_date": run_data["run_date"],
        "run_id": run_data["run_id"],
        "file": str(run_file),
        "total_questions": s["total_questions"],
        "hit_at_5": s["retrieval"]["hit_at_5"],
        "mrr": s["retrieval"]["mrr"],
        "avg_correctness": s["generation"].get("avg_correctness"),
    })
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)

    return run_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Valutazione end-to-end RAG CNI")
    parser.add_argument("--dataset", default="config/golden_dataset.json")
    parser.add_argument("--limit", type=int, default=None, help="Numero massimo di domande")
    parser.add_argument("--no-judge", action="store_true", help="Salta la valutazione LLM-as-judge")
    parser.add_argument("--run-id", default=None, help="ID del run (default: timestamp). Permette il resume.")
    parser.add_argument("--resume", default=None, help="Path di un file .partial.json da cui riprendere")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    items = load_dataset(args.dataset)
    if args.limit:
        items = items[: args.limit]

    dataset_meta = {}
    with open(args.dataset, encoding="utf-8") as fh:
        dataset_meta = json.load(fh).get("version", "")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    now = datetime.now()
    day_dir = RESULTS_DIR / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    partial_path = day_dir / f"eval_{run_id}.partial.json"

    rows: list[dict[str, Any]] = []
    if args.resume and Path(args.resume).exists():
        with open(args.resume, encoding="utf-8") as fh:
            partial = json.load(fh)
        rows = partial.get("rows", [])
        done_ids = {r["question_id"] for r in rows}
        items = [i for i in items if i["id"] not in done_ids]
        console.print(f"[yellow]Resume: {len(rows)} domande gia' completate, ne restano {len(items)}[/yellow]")

    console.print("[bold cyan]CNI RAG - Valutazione end-to-end[/bold cyan]")
    console.print(f"Domande: {len(items)} | Judge LLM: {'OFF' if args.no_judge else 'ON'} | run_id: {run_id}\n")

    try:
        health = httpx.get(f"{API_BASE}/health", timeout=10).json()
        console.print(f"API: {health.get('status')} | documenti indicizzati: {health.get('documents_indexed')}\n")
    except Exception as exc:
        console.print(f"[red]API non raggiungibile su {API_BASE}: {exc}[/red]")
        console.print("Avvia l'API con: python scripts/run_api.py --no-reload")
        sys.exit(1)

    judge = None if args.no_judge else LLMJudge()

    fallback_msg = ConfigLoader.get_rag_config().get("fallback", {}).get("message", "")
    start_all = time.perf_counter()

    for item in items:
        qid = item["id"]
        question = item["question"]
        console.print(f"[cyan]{qid}[/cyan] {question}")
        t0 = time.perf_counter()
        resp = httpx.post(f"{API_BASE}/query", json={"question": question}, timeout=900.0)
        resp.raise_for_status()
        out = resp.json()
        latency = round(time.perf_counter() - t0, 2)

        response = out.get("response", "")
        fallback_triggered = (
            out.get("fallback_triggered") or (fallback_msg and response.strip() == fallback_msg.strip())
        )

        ret = retrieval_metrics(out.get("retrieved_docs", []), item.get("expected_sources", []))

        judge_res = None
        if judge is not None and not fallback_triggered:
            context = "\n---\n".join(d.get("content", "") for d in out.get("context_docs") or out.get("retrieved_docs", []))
            judge_res = judge.evaluate(question, response, context, item.get("reference_answer", ""))
        elif fallback_triggered:
            judge_res = {
                "faithfulness": {"score": None, "reason": "fallback"},
                "answer_relevance": {"score": None, "reason": "fallback"},
                "correctness": {"score": None, "reason": "fallback"},
            }

        must = item.get("must_contain", [])
        must_hits = [kw for kw in must if kw.lower() in response.lower()]

        preview = response.replace("\n", " ")[:120]
        scores_txt = ""
        if judge_res:
            scores_txt = (
                f" | F={judge_res['faithfulness']['score']} "
                f"A={judge_res['answer_relevance']['score']} "
                f"C={judge_res['correctness']['score']}"
            )
        console.print(
            f"  rank={ret['first_relevant_rank']} mrr={ret['mrr']:.2f}{scores_txt}"
            f" | lat={latency}s\n  > {preview}"
        )

        rows.append({
            "question_id": qid,
            "question": question,
            "category": item.get("category", ""),
            "reference_answer": item.get("reference_answer", ""),
            "expected_sources": item.get("expected_sources", []),
            "must_contain": must,
            "must_contain_hits": must_hits,
            "must_contain_pass": len(must_hits) == len(must) if must else None,
            "response": response,
            "citations": out.get("citations", []),
            "retrieved_sources": [d.get("source") for d in out.get("retrieved_docs", [])],
            "reranked_sources": [d.get("source") for d in out.get("context_docs", [])],
            "fallback_triggered": fallback_triggered,
            "retrieval": ret,
            "judgment": judge_res,
            "latency_s": latency,
            "pipeline": {
                "category": out.get("category"),
                "grade_result": out.get("grade_result"),
                "self_check_result": out.get("self_check_result"),
            },
        })
        console.print()

        # Checkpoint incrementale per resume
        tmp = partial_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"run_id": run_id, "rows": rows}, fh, ensure_ascii=False)
        tmp.replace(partial_path)

    duration = round(time.perf_counter() - start_all, 1)
    n = len(rows)

    avg = lambda key: (  # noqa: E731
        round(sum(r["judgment"][key]["score"] for r in rows if r["judgment"] and r["judgment"][key]["score"] is not None)
              / max(1, sum(1 for r in rows if r["judgment"] and r["judgment"][key]["score"] is not None)), 3)
    )

    aggregate = {
        "total_questions": n,
        "fallback_rate": round(sum(1 for r in rows if r["fallback_triggered"]) / n, 3) if n else 0.0,
        "retrieval": {
            key: round(sum(r["retrieval"][key] for r in rows) / n, 4) if n else 0.0
            for key in ["mrr", "recall", "hit_at_3", "hit_at_5", "hit_at_10"]
        },
        "generation": {
            "avg_faithfulness": None if args.no_judge else avg("faithfulness"),
            "avg_answer_relevance": None if args.no_judge else avg("answer_relevance"),
            "avg_correctness": None if args.no_judge else avg("correctness"),
            "pass_rate_correctness_ge4": None if args.no_judge else round(
                sum(1 for r in rows if r["judgment"] and (r["judgment"]["correctness"]["score"] or 0) >= 4)
                / max(1, sum(1 for r in rows if r["judgment"])), 3),
            "must_contain_pass_rate": round(
                sum(1 for r in rows if r["must_contain_pass"]) / max(1, sum(1 for r in rows if r["must_contain_pass"] is not None)), 3),
        },
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / n, 2) if n else 0.0,
    }

    run_data = {
        "run_id": run_id,
        "run_date": datetime.now().isoformat(timespec="seconds"),
        "dataset": args.dataset,
        "dataset_version": dataset_meta,
        "judge_enabled": not args.no_judge,
        "config_snapshot": ConfigLoader.get_rag_config(),
        "aggregate": aggregate,
        "duration_s": duration,
        "results": rows,
    }

    run_file = save_run(run_data, rows)

    table = Table(title=f"Valutazione end-to-end — {run_id}", title_style="bold")
    table.add_column("Metrica")
    table.add_column("Valore", justify="right")
    table.add_row("Domande", str(n))
    table.add_row("Fallback rate", f"{aggregate['fallback_rate']:.1%}")
    table.add_row("Hit@3 / Hit@5 / Hit@10", f"{aggregate['retrieval']['hit_at_3']:.2f} / {aggregate['retrieval']['hit_at_5']:.2f} / {aggregate['retrieval']['hit_at_10']:.2f}")
    table.add_row("MRR", f"{aggregate['retrieval']['mrr']:.3f}")
    table.add_row("Recall fonti", f"{aggregate['retrieval']['recall']:.3f}")
    if not args.no_judge:
        table.add_row("Faithfulness (0-5)", f"{aggregate['generation']['avg_faithfulness']}")
        table.add_row("Answer relevance (0-5)", f"{aggregate['generation']['avg_answer_relevance']}")
        table.add_row("Correctness (0-5)", f"{aggregate['generation']['avg_correctness']}")
        table.add_row("Pass rate (C>=4)", f"{aggregate['generation']['pass_rate_correctness_ge4']:.1%}")
    table.add_row("Must-contain pass", f"{aggregate['generation']['must_contain_pass_rate']:.1%}")
    table.add_row("Latenza media (s)", f"{aggregate['avg_latency_s']}")
    console.print(table)
    console.print(f"\n[green]Dettaglio salvato in:[/green] {run_file}")
    console.print("[green]Storico:[/green] results/history.csv, results/summary.csv")


if __name__ == "__main__":
    main()
