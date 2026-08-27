#!/usr/bin/env python3
"""
Ablation study sul retrieval — senza LLM, quindi in minuti anziche' in ore.

Perche' esiste
--------------
Una valutazione end-to-end costa ~456 s per domanda: 30 domande sono quasi 4
ore, e confrontare 8 configurazioni sarebbe impossibile. Ma il retrieval NON
richiede il modello generativo: servono solo l'embedder, Qdrant e il
reranker. Ogni configurazione si misura in secondi.

E' quindi qui che vive, concretamente, il capitolo degli esperimenti: le
scelte progettuali sul retrieval si giustificano con evidenza misurata
invece che con un'argomentazione.

Cosa confronta
--------------
  - top_k dei candidati (10 / 25 / 50)
  - reranking acceso o spento, e con quale modello
  - quanti documenti il reranker passa al generatore (rerank_top_k)
  - filtro di categoria rigido oppure disattivato

Ogni configurazione e' valutata sulle STESSE domande, quindi i confronti sono
appaiati (Wilcoxon per gli ordinali, McNemar esatto per i binari) e riportano
intervallo di confidenza e dimensione dell'effetto.

Le metriche sono calcolate su due stadi: i candidati recuperati e i documenti
che sopravvivono al reranking — cioe' cio' che l'LLM riceverebbe davvero.

Usage:
    python benchmarks/ablation_retrieval.py
    python benchmarks/ablation_retrieval.py --dataset config/golden_dataset_v2.json
    python benchmarks/ablation_retrieval.py --preset veloce     # 4 configurazioni
    python benchmarks/ablation_retrieval.py --markdown          # tabella per la tesi
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from benchmarks import metrics as M
from benchmarks import stats as S
from src.core.config_loader import ConfigLoader

console = Console()
RESULTS_DIR = Path("results")
K_VALUES = (1, 3, 5, 10)


# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Una configurazione di retrieval da valutare."""
    nome: str
    top_k: int = 25
    reranker: str | None = "BAAI/bge-reranker-base"   # None = reranking disattivato
    rerank_top_k: int = 5
    filtro_categoria: bool = True
    score_threshold: float = 0.3
    note: str = ""

    def descrizione(self) -> str:
        r = self.reranker.split("/")[-1] if self.reranker else "nessuno"
        f = "sì" if self.filtro_categoria else "no"
        return f"top_k={self.top_k} · rerank={r} → {self.rerank_top_k} · filtro categoria={f}"


def preset_configs(base: dict[str, Any], preset: str, con_mmarco: bool = False) -> list[Config]:
    """La configurazione attuale del progetto e' sempre la prima (baseline)."""
    attuale = Config(
        nome="attuale",
        top_k=base["top_k"],
        reranker=base["reranker"] if base["rerank_enabled"] else None,
        rerank_top_k=base["rerank_top_k"],
        filtro_categoria=True,
        score_threshold=base["score_threshold"],
        note="configurazione in config/rag_config.yaml",
    )

    veloci = [
        attuale,
        Config("senza reranker", top_k=base["top_k"], reranker=None,
               rerank_top_k=base["rerank_top_k"], note="isola il contributo del reranker"),
        Config("senza filtro categoria", top_k=base["top_k"], reranker=base["reranker"],
               rerank_top_k=base["rerank_top_k"], filtro_categoria=False,
               note="il filtro rigido aiuta o danneggia?"),
        Config("top_k = 10", top_k=10, reranker=base["reranker"],
               rerank_top_k=base["rerank_top_k"], note="la configurazione precedente al fix"),
    ]
    extra = []
    if con_mmarco:
        # Richiede il download del modello al primo uso: senza rete fallisce.
        extra.append(Config(
            "reranker mmarco (italiano)", top_k=base["top_k"],
            reranker="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            rerank_top_k=base["rerank_top_k"],
            note="addestrato su mMARCO, che include l'italiano; meta' del peso"))

    if preset == "veloce":
        return veloci + extra

    return veloci + extra + [
        Config("top_k = 50", top_k=50, reranker=base["reranker"], rerank_top_k=base["rerank_top_k"],
               note="piu' candidati aiutano il reranker?"),
        Config("contesto = 3 doc", top_k=base["top_k"], reranker=base["reranker"], rerank_top_k=3,
               note="contesto piu' stretto"),
        Config("contesto = 10 doc", top_k=base["top_k"], reranker=base["reranker"], rerank_top_k=10,
               note="contesto piu' ampio"),
        Config("nessun filtro, nessun rerank", top_k=base["top_k"], reranker=None,
               rerank_top_k=base["rerank_top_k"], filtro_categoria=False,
               note="retrieval denso puro: il minimo assoluto"),
        Config("senza filtro + contesto 10", top_k=base["top_k"], reranker=base["reranker"],
               rerank_top_k=10, filtro_categoria=False,
               note="combina le due modifiche che sembrano aiutare"),
    ]


# ---------------------------------------------------------------------------

class Motore:
    """Embedder, Qdrant e reranker caricati una volta sola e riusati."""

    def __init__(self):
        from src.core.model_factory import ModelFactory
        from src.rag.query_classifier import QueryClassifier
        from src.vectorstore.qdrant_client import QdrantClientManager

        console.print("[dim]caricamento embedder…[/dim]")
        self.embeddings = ModelFactory.create_embeddings()
        self.classifier = QueryClassifier()
        self.manager = QdrantClientManager()
        self.collection = self.manager.collection_name
        self._rerankers: dict[str, Any] = {}

    def reranker(self, nome: str):
        if nome not in self._rerankers:
            from sentence_transformers import CrossEncoder
            console.print(f"[dim]caricamento reranker {nome}…[/dim]")
            self._rerankers[nome] = CrossEncoder(nome)
        return self._rerankers[nome]

    def cerca(self, domanda: str, cfg: Config) -> tuple[list[dict], list[dict], str]:
        """Restituisce (candidati, contesto dopo rerank, categoria applicata)."""
        categoria = self.classifier.classify(domanda)

        filtro = None
        if cfg.filtro_categoria and categoria != "generico":
            from qdrant_client.http import models as rest
            filtro = rest.Filter(must=[
                rest.FieldCondition(key="category", match=rest.MatchValue(value=categoria))
            ])

        vettore = self.embeddings.embed_query(domanda)
        punti = self.manager.get_client().query_points(
            collection_name=self.collection,
            query=vettore,
            limit=cfg.top_k,
            score_threshold=cfg.score_threshold,
            query_filter=filtro,
        ).points

        candidati = [{
            "content": p.payload.get("content", ""),
            "source": p.payload.get("source", ""),
            "title": p.payload.get("title", ""),
            "category": p.payload.get("category", ""),
            "score": p.score,
        } for p in punti]

        if not cfg.reranker or not candidati:
            contesto = candidati[: cfg.rerank_top_k]
        else:
            ce = self.reranker(cfg.reranker)
            punteggi = ce.predict([(domanda, c["content"]) for c in candidati])
            for c, s in zip(candidati, punteggi):
                c["rerank_score"] = float(s)
            contesto = sorted(candidati, key=lambda c: c["rerank_score"], reverse=True)[: cfg.rerank_top_k]

        return candidati, contesto, categoria


# ---------------------------------------------------------------------------

def valuta(motore: Motore, items: list[dict], cfg: Config) -> dict[str, Any]:
    t0 = time.perf_counter()
    per_domanda = []

    for it in items:
        expected = it.get("expected_sources", [])
        candidati, contesto, categoria = motore.cerca(it["question"], cfg)
        stadi = M.evaluate_stages(candidati, contesto, expected, K_VALUES)
        per_domanda.append({
            "question_id": it["id"],
            "question": it["question"],
            "categoria_applicata": categoria,
            "n_candidati": len(candidati),
            "retrieved": stadi["retrieved"],
            "context": stadi["context"],
        })

    durata = time.perf_counter() - t0
    pre = [r["retrieved"] for r in per_domanda]
    post = [r["context"] for r in per_domanda]

    def riepilogo(righe):
        chiavi = ["mrr"] + [f"{m}_at_{k}" for k in K_VALUES for m in ("hit", "recall", "ndcg")]
        return {c: S.summarize_metric(M.column(righe, c), c, binary=c.startswith("hit")) for c in chiavi}

    return {
        "config": asdict(cfg),
        "descrizione": cfg.descrizione(),
        "n_domande": len(items),
        "durata_s": round(durata, 1),
        "s_per_domanda": round(durata / max(1, len(items)), 2),
        "candidati_medi": round(sum(r["n_candidati"] for r in per_domanda) / max(1, len(per_domanda)), 1),
        "domande_senza_candidati": sum(1 for r in per_domanda if r["n_candidati"] == 0),
        "punto_retrieved": M.aggregate_rankings(pre, K_VALUES),
        "punto_context": M.aggregate_rankings(post, K_VALUES),
        "ci_retrieved": riepilogo(pre),
        "ci_context": riepilogo(post),
        "per_domanda": per_domanda,
    }


def confronta(base: dict, alt: dict) -> dict[str, Any]:
    """Confronto appaiato fra due configurazioni, sullo stadio 'context'."""
    out = {}
    for chiave, binaria in [("hit_at_3", True), ("hit_at_5", True),
                            ("mrr", False), ("recall_at_5", False), ("ndcg_at_5", False)]:
        a = M.column([r["context"] for r in base["per_domanda"]], chiave)
        b = M.column([r["context"] for r in alt["per_domanda"]], chiave)
        out[chiave] = S.paired_report(a, b, name=chiave, binary=binaria,
                                      label_a="base", label_b="alt")
    return out


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Ablation sul retrieval (senza LLM)")
    ap.add_argument("--dataset", default="config/golden_dataset_v2.json")
    ap.add_argument("--preset", choices=["veloce", "completo"], default="completo")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--markdown", action="store_true", help="stampa la tabella in Markdown")
    ap.add_argument("--out", default=None)
    ap.add_argument("--con-mmarco", action="store_true",
                    help="include il reranker mmarco (scarica ~470 MB al primo uso)")
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data["items"][: args.limit] if args.limit else data["items"]

    rag = ConfigLoader.get_rag_config()
    base_cfg = {
        "top_k": rag.get("retrieval", {}).get("top_k", 25),
        "score_threshold": rag.get("retrieval", {}).get("score_threshold", 0.3),
        "rerank_enabled": rag.get("reranking", {}).get("enabled", True),
        "reranker": rag.get("reranking", {}).get("model", "BAAI/bge-reranker-base"),
        "rerank_top_k": rag.get("reranking", {}).get("top_k", 5),
    }

    configs = preset_configs(base_cfg, args.preset, con_mmarco=args.con_mmarco)

    console.print(f"\n[bold cyan]Ablation sul retrieval[/bold cyan]")
    console.print(f"dataset: {args.dataset} · domande: [bold]{len(items)}[/bold] · "
                  f"configurazioni: [bold]{len(configs)}[/bold]\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else RESULTS_DIR / f"ablation_retrieval_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    parziale = out.with_suffix(".partial.json")

    motore = Motore()
    risultati, falliti = [], []
    for i, cfg in enumerate(configs, 1):
        console.print(f"[cyan]{i}/{len(configs)}[/cyan] {cfg.nome} — [dim]{cfg.descrizione()}[/dim]")
        try:
            r = valuta(motore, items, cfg)
        except Exception as exc:
            # Una configurazione che fallisce (tipicamente: modello non scaricabile
            # perche' manca la rete) non deve far perdere quelle gia' completate.
            motivo = str(exc).split("\n")[0][:200]
            console.print(f"        [red]saltata: {motivo}[/red]")
            falliti.append({"nome": cfg.nome, "descrizione": cfg.descrizione(), "errore": motivo})
            continue

        risultati.append(r)
        c = r["ci_context"]
        console.print(
            f"        Hit@5 {S.format_ci(c['hit_at_5'], pct=True)} · "
            f"MRR {S.format_ci(c['mrr'])} · {r['durata_s']}s"
            + (f" · [red]{r['domande_senza_candidati']} domande senza candidati[/red]"
               if r["domande_senza_candidati"] else "")
        )

        # Checkpoint dopo ogni configurazione: un crash a meta' non azzera il lavoro.
        try:
            tmp = parziale.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"parziale": True, "completate": len(risultati),
                           "totali": len(configs), "risultati": risultati,
                           "falliti": falliti}, fh, ensure_ascii=False)
            tmp.replace(parziale)
        except OSError:
            pass

    if not risultati:
        console.print("[red]Nessuna configurazione completata.[/red]")
        sys.exit(1)
    if falliti:
        console.print(f"\n[yellow]{len(falliti)} configurazioni saltate:[/yellow] "
                      + ", ".join(f["nome"] for f in falliti))

    # --- tabella principale ------------------------------------------------
    t = Table(title=f"Contesto passato al generatore — n={len(items)}, IC 95%", title_style="bold")
    t.add_column("configurazione")
    t.add_column("Hit@3", justify="right")
    t.add_column("Hit@5", justify="right")
    t.add_column("MRR", justify="right")
    t.add_column("nDCG@5", justify="right")
    t.add_column("s/dom.", justify="right")
    for r in risultati:
        c = r["ci_context"]
        t.add_row(r["config"]["nome"],
                  S.format_ci(c["hit_at_3"], pct=True), S.format_ci(c["hit_at_5"], pct=True),
                  S.format_ci(c["mrr"]), S.format_ci(c["ndcg_at_5"]), f"{r['s_per_domanda']}")
    console.print()
    console.print(t)

    # --- confronti appaiati contro la baseline -----------------------------
    base = risultati[0]
    ct = Table(title=f"Confronto appaiato contro «{base['config']['nome']}»", title_style="bold")
    ct.add_column("configurazione")
    ct.add_column("Δ Hit@5", justify="right")
    ct.add_column("p", justify="right")
    ct.add_column("Δ MRR", justify="right")
    ct.add_column("p", justify="right")
    ct.add_column("effetto", justify="right")

    confronti = {}
    for r in risultati[1:]:
        cmp_ = confronta(base, r)
        confronti[r["config"]["nome"]] = cmp_
        h, m = cmp_["hit_at_5"], cmp_["mrr"]
        ct.add_row(
            r["config"]["nome"],
            f"{h['mean_difference']:+.3f}", f"{h['significance']['p_value']:.4f}",
            f"{m['mean_difference']:+.3f}", f"{m['significance']['p_value']:.4f}",
            m["effect_size"]["magnitude"],
        )
    console.print()
    console.print(ct)

    console.print(
        "\n[dim]Δ positivo = la configurazione alternativa fa meglio della baseline. "
        "p < 0,05 indica una differenza distinguibile dal rumore; l'effetto ne dice l'entità.[/dim]"
    )

    # --- salvataggio -------------------------------------------------------
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "data": datetime.now().isoformat(timespec="seconds"),
            "dataset": args.dataset,
            "dataset_version": data.get("version"),
            "n_domande": len(items),
            "baseline": base["config"]["nome"],
            "configurazioni_saltate": falliti,
            "risultati": risultati,
            "confronti_vs_baseline": confronti,
            "ambiente_statistico": S.describe_environment(),
        }, fh, ensure_ascii=False, indent=2)
    parziale.unlink(missing_ok=True)
    console.print(f"\n[green]Salvato in:[/green] {out}")

    if args.markdown:
        console.print("\n[bold]Tabella per la tesi[/bold]\n")
        print(f"| Configurazione | Hit@3 | Hit@5 | MRR | nDCG@5 | s/domanda |")
        print("|---|---|---|---|---|---|")
        for r in risultati:
            c = r["ci_context"]
            print(f"| {r['config']['nome']} | {S.format_ci(c['hit_at_3'], pct=True)} | "
                  f"{S.format_ci(c['hit_at_5'], pct=True)} | {S.format_ci(c['mrr'])} | "
                  f"{S.format_ci(c['ndcg_at_5'])} | {r['s_per_domanda']} |")
        print(f"\nn = {len(items)} domande · intervalli di confidenza al 95% · "
              f"bootstrap {S.DEFAULT_RESAMPLES} ricampionamenti, seme {S.DEFAULT_SEED}")


if __name__ == "__main__":
    main()
