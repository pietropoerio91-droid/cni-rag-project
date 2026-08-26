#!/usr/bin/env python3
"""
Valutazione end-to-end del sistema RAG CNI (retrieval + generazione).

A differenza di run_benchmark.py (che valuta solo il retrieval con keyword
matching), questo harness valuta la qualita' della risposta generata tramite
LLM-as-judge (qwen2.5:3b locale) e calcola le metriche di retrieval contro le
fonti attese del golden dataset.

Metriche di retrieval (definizioni in `benchmarks/metrics.py`):
  - hit_at_k, recall_at_k, precision_at_k, mrr, ndcg_at_k

Sono calcolate su DUE stadi della pipeline:
  - "retrieved": l'uscita del retriever denso (i candidati, top_k = 25)
  - "context":   cio' che l'LLM riceve davvero, dopo il reranking (top-5)
La differenza fra i due e' il guadagno del reranker, misurato direttamente.

Metriche qualitative (LLM-as-judge, scala 0-5):
  - faithfulness:      la risposta e' coerente con i documenti recuperati?
  - answer_relevance:  la risposta risponde effettivamente alla domanda?
  - correctness:       la risposta e' coerente con la reference answer?

ATTENZIONE: i punteggi del judge non sono utilizzabili finche' il judge non
e' stato validato contro giudizio umano. Vedi `compute_judge_agreement.py`.
Ogni run riporta `judge_validated: false` finche' quella validazione manca.

Tutte le medie aggregate sono accompagnate da un intervallo di confidenza al
95% (bootstrap per le medie, Wilson per le proporzioni): vedi
`benchmarks/stats.py`.

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

from benchmarks import metrics as M
from benchmarks import stats as S
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


K_VALUES = (1, 3, 5, 10)

# Le metriche di retrieval vivono in benchmarks/metrics.py, condivise con
# l'API. La versione precedente le implementava qui con tre difetti:
#   - recall non troncato a k (scorreva tutti i 25 candidati)
#   - matching asimmetrico (hit/mrr su source|title, recall solo su source)
#   - calcolo sui soli retrieved_docs, cioe' prima del reranking
# Vedi il docstring di metrics.py per le definizioni corrette.


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
        # pre-reranking (uscita del retriever denso)
        "hit_at_3", "hit_at_5", "hit_at_10", "mrr", "recall_at_5", "recall_at_10",
        # post-reranking (cio' che riceve l'LLM)
        "ctx_hit_at_3", "ctx_hit_at_5", "ctx_mrr", "ctx_recall_at_5", "ctx_ndcg_at_5",
        "avg_faithfulness", "avg_answer_relevance", "avg_correctness",
        "pass_rate_correctness_ge4", "must_contain_pass_rate",
        "judge_validated", "avg_latency_s", "duration_s",
    ]
    s = run_data["aggregate"]
    ctx_point = (s.get("retrieval_stages", {}).get("context") or {}).get("point", {})
    row = {
        "run_date": run_data["run_date"],
        "run_id": run_data["run_id"],
        "total_questions": s["total_questions"],
        "fallback_rate": s["fallback_rate"],
        "hit_at_3": s["retrieval"].get("hit_at_3"),
        "hit_at_5": s["retrieval"].get("hit_at_5"),
        "hit_at_10": s["retrieval"].get("hit_at_10"),
        "mrr": s["retrieval"].get("mrr"),
        "recall_at_5": s["retrieval"].get("recall_at_5"),
        "recall_at_10": s["retrieval"].get("recall_at_10"),
        "ctx_hit_at_3": ctx_point.get("hit_at_3"),
        "ctx_hit_at_5": ctx_point.get("hit_at_5"),
        "ctx_mrr": ctx_point.get("mrr"),
        "ctx_recall_at_5": ctx_point.get("recall_at_5"),
        "ctx_ndcg_at_5": ctx_point.get("ndcg_at_5"),
        "must_contain_pass_rate": s["generation"].get("must_contain_pass_rate"),
        "judge_validated": run_data.get("judge_validated", False),
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

        retrieved_docs = out.get("retrieved_docs") or []
        context_docs = out.get("context_docs") or []
        expected = item.get("expected_sources", [])

        stages = M.evaluate_stages(retrieved_docs, context_docs, expected, K_VALUES)
        gain = M.reranker_gain(stages, k=5)
        ret = stages["retrieved"]
        ctx = stages["context"]

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
            f"  rank pre={ret['first_relevant_rank']} post={ctx['first_relevant_rank']}"
            f" | H@5 pre={ret['hit_at_5']} post={ctx['hit_at_5']}{scores_txt}"
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
            "retrieved_sources": [d.get("source") for d in retrieved_docs],
            "reranked_sources": [d.get("source") for d in context_docs],
            "fallback_triggered": fallback_triggered,
            "retrieval": ret,          # pre-reranking (compatibilita' con i run precedenti)
            "retrieval_context": ctx,  # post-reranking: cio' che riceve l'LLM
            "reranker_gain": gain,
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

    # --- metriche di retrieval con intervalli di confidenza, per stadio -----
    def stage_summary(field: str) -> dict[str, Any]:
        """Riepilogo di uno stadio: media + IC 95% per ogni metrica."""
        per_q = [r[field] for r in rows if r.get(field)]
        if not per_q:
            return {}
        out_: dict[str, Any] = {"point": M.aggregate_rankings(per_q, K_VALUES)}
        keys = ["mrr"] + [f"{m}_at_{k}" for k in K_VALUES for m in ("hit", "recall", "precision", "ndcg")]
        out_["ci"] = {
            key: S.summarize_metric(M.column(per_q, key), key, binary=key.startswith("hit"))
            for key in keys
        }
        return out_

    retrieval_stages = {
        "retrieved": stage_summary("retrieval"),
        "context": stage_summary("retrieval_context"),
    }

    # --- effetto del reranker: confronto appaiato pre/post sulle stesse domande
    pre_q = [r["retrieval"] for r in rows if r.get("retrieval")]
    post_q = [r["retrieval_context"] for r in rows if r.get("retrieval_context")]
    reranker_effect: dict[str, Any] = {}
    if len(pre_q) == len(post_q) and len(pre_q) >= 2:
        for key, is_binary in [("hit_at_5", True), ("mrr", False),
                               ("recall_at_5", False), ("ndcg_at_5", False)]:
            reranker_effect[key] = S.paired_report(
                M.column(pre_q, key), M.column(post_q, key),
                name=key, binary=is_binary, label_a="pre_rerank", label_b="post_rerank",
            )

    fallback_hits = sum(1 for r in rows if r["fallback_triggered"])

    aggregate = {
        "total_questions": n,
        "fallback_rate": round(fallback_hits / n, 3) if n else 0.0,
        "fallback_rate_ci": list(S.wilson_ci(fallback_hits, n)) if n else None,
        "retrieval_stages": retrieval_stages,
        "reranker_effect": reranker_effect,
        # Compatibilita' con i run precedenti: valori puntuali pre-reranking.
        "retrieval": {
            key: round(sum(r["retrieval"].get(key, 0) or 0 for r in rows) / n, 4) if n else 0.0
            for key in ["mrr", "hit_at_3", "hit_at_5", "hit_at_10", "recall_at_5", "recall_at_10"]
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
            # IC sui punteggi del judge: medie su scala ordinale 0-5, bootstrap.
            "ci": {} if args.no_judge else {
                key: S.summarize_metric(
                    [r["judgment"][key]["score"] for r in rows
                     if r["judgment"] and r["judgment"][key]["score"] is not None],
                    key,
                )
                for key in ("faithfulness", "answer_relevance", "correctness")
            },
            # must_contain e' deterministico: e' l'unica metrica di generazione
            # utilizzabile finche' il judge non e' validato.
            "must_contain_ci": list(S.wilson_ci(
                sum(1 for r in rows if r["must_contain_pass"]),
                max(1, sum(1 for r in rows if r["must_contain_pass"] is not None)),
            )),
        },
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / n, 2) if n else 0.0,
        "latency_ci": list(S.bootstrap_ci([r["latency_s"] for r in rows])) if n >= 2 else None,
    }

    run_data = {
        "run_id": run_id,
        "run_date": datetime.now().isoformat(timespec="seconds"),
        "dataset": args.dataset,
        "dataset_version": dataset_meta,
        "judge_enabled": not args.no_judge,
        # I punteggi del judge non sono riportabili finche' non e' dimostrato
        # l'accordo con giudizio umano (compute_judge_agreement.py). Il flag
        # resta False finche' quella validazione non e' agli atti.
        "judge_validated": False,
        "judge_model": ConfigLoader.get_rag_config().get("llm", {}).get("model"),
        "config_snapshot": ConfigLoader.get_rag_config(),
        "stats_environment": S.describe_environment(),
        "k_values": list(K_VALUES),
        "aggregate": aggregate,
        "duration_s": duration,
        "results": rows,
    }

    run_file = save_run(run_data, rows)

    def ci_of(stage: str, key: str) -> str:
        node = (aggregate["retrieval_stages"].get(stage) or {}).get("ci", {}).get(key)
        return S.format_ci(node, pct=key.startswith("hit")) if node else "—"

    table = Table(title=f"Valutazione end-to-end — {run_id}  (n={n}, IC 95%)", title_style="bold")
    table.add_column("Metrica")
    table.add_column("Pre-rerank (candidati)", justify="right")
    table.add_column("Post-rerank (contesto LLM)", justify="right")

    for key in ("hit_at_3", "hit_at_5", "mrr", "recall_at_5", "ndcg_at_5"):
        table.add_row(key, ci_of("retrieved", key), ci_of("context", key))
    console.print(table)

    if aggregate.get("reranker_effect"):
        eff = Table(title="Effetto del reranker (confronto appaiato)", title_style="bold")
        eff.add_column("Metrica")
        eff.add_column("Differenza", justify="right")
        eff.add_column("IC 95% diff.", justify="right")
        eff.add_column("p", justify="right")
        eff.add_column("Effetto", justify="right")
        for key, rep in aggregate["reranker_effect"].items():
            ci = rep.get("difference_ci")
            eff.add_row(
                key,
                f"{rep['mean_difference']:+.3f}",
                f"[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "—",
                f"{rep['significance']['p_value']:.4f}",
                rep["effect_size"]["magnitude"],
            )
        console.print(eff)

    gen = Table(title="Generazione", title_style="bold")
    gen.add_column("Metrica")
    gen.add_column("Valore", justify="right")
    fb_ci = aggregate.get("fallback_rate_ci")
    gen.add_row("Fallback rate", f"{aggregate['fallback_rate']:.1%}"
                + (f"  [{fb_ci[0]:.1%}, {fb_ci[1]:.1%}]" if fb_ci else ""))
    mc_ci = aggregate["generation"].get("must_contain_ci")
    gen.add_row("Must-contain pass", f"{aggregate['generation']['must_contain_pass_rate']:.1%}"
                + (f"  [{mc_ci[0]:.1%}, {mc_ci[1]:.1%}]" if mc_ci else ""))
    if not args.no_judge:
        for key, label in [("faithfulness", "Faithfulness (0-5)"),
                           ("answer_relevance", "Answer relevance (0-5)"),
                           ("correctness", "Correctness (0-5)")]:
            node = aggregate["generation"].get("ci", {}).get(key)
            gen.add_row(label, S.format_ci(node) if node else "—")
    gen.add_row("Latenza media (s)", f"{aggregate['avg_latency_s']}")
    console.print(gen)

    if not args.no_judge:
        console.print(
            "\n[yellow]I punteggi del judge NON sono validati.[/yellow] "
            f"Il giudice e' [bold]{run_data['judge_model']}[/bold]; se coincide con il modello "
            "che genera le risposte c'e' bias di autovalutazione.\n"
            "Prima di riportarli: [cyan]python benchmarks/export_validation_sheet.py[/cyan] -> "
            "compila i voti umani -> [cyan]python benchmarks/compute_judge_agreement.py --sheet <csv>[/cyan]"
        )

    console.print(f"\n[green]Dettaglio salvato in:[/green] {run_file}")
    console.print("[green]Storico:[/green] results/history.csv, results/summary.csv")


if __name__ == "__main__":
    main()
