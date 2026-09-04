#!/usr/bin/env python3
"""
Confronto fra modelli generativi locali, a contesto congelato.

Perche' serve
-------------
La scelta dell'embedder, del reranker, di `top_k` e del filtro di categoria e'
stata giustificata misurando le alternative. La scelta del generatore no: in
`confronto-llm-generativi-locali.md` c'e' una rassegna della letteratura, e
quella rassegna dichiara due limiti espliciti — per qwen2.5:3b non esiste un
punteggio pubblicato in italiano, e non esiste alcun benchmark di velocita'
per l'hardware di questo progetto. Entrambi si chiudono solo misurando.

Il contesto e' congelato
------------------------
Il recupero viene eseguito UNA volta sola, con la configurazione di
produzione, e gli stessi identici documenti vengono passati a tutti i modelli.
Senza questo accorgimento ogni modello riceverebbe il proprio contesto e la
differenza fra due modelli sarebbe confusa con la variabilita' del retrieval:
si misurerebbe il sistema, non il generatore. Congelando il contesto la
domanda diventa quella giusta — *a parita' di documenti, quale modello li usa
meglio?*

Due fasi separate
-----------------
A. **Prestazioni** (minuti): pochi prompt fissi per modello, per ottenere
   token/secondo, tempo di caricamento e memoria occupata sull'hardware reale.
   Sono i numeri che la rassegna bibliografica dichiara come non reperibili.

B. **Qualita'** (ore): le domande del golden dataset con contesto congelato.
   Su CPU dual-core una risposta costa minuti, quindi conviene `--limit`.

Le due fasi sono indipendenti: `--solo-prestazioni` esegue solo la A.

Nota sull'onesta' della misura
------------------------------
`--max-token` vale per tutti i modelli allo stesso modo, quindi il confronto
resta interno coerente; ma se lo si abbassa rispetto al valore di produzione,
le latenze non sono comparabili con quelle del run end-to-end. Il valore usato
viene registrato nel JSON.

Uso:
    # solo la tabella hardware, pochi minuti
    python benchmarks/compare_generators.py --solo-prestazioni

    # confronto di qualita' su 12 domande
    python benchmarks/compare_generators.py --limit 12 --markdown

    # modelli diversi
    python benchmarks/compare_generators.py --models qwen2.5:3b llama3.2:3b phi3.5
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from rich.console import Console
from rich.table import Table

from benchmarks import stats as S
from benchmarks.ablation_retrieval import Config, Motore
from src.core.config_loader import ConfigLoader
from src.rag.prompt_builder import PromptBuilder

console = Console()

OLLAMA = "http://localhost:11434"
RESULTS_DIR = Path("results")

MODELLI_DEFAULT = ["qwen2.5:3b", "llama3.2:3b", "phi3.5"]

# Criteri non metrici che vanno in tabella accanto ai numeri: per un sistema
# destinato a un ente pubblico la licenza e' un criterio di scelta al pari
# della qualita'. Qwen2.5 e' Apache 2.0 in tutte le taglie tranne la 3B, che
# ha una licenza di sola ricerca — cioe' proprio quella in uso qui.
LICENZE = {
    "qwen2.5:3b": "Qwen Research (NON commerciale)",
    "llama3.2:3b": "Llama 3.2 Community",
    "phi3.5": "MIT",
    "phi4-mini": "MIT",
    "gemma2:2b": "Gemma Terms (non OSI)",
}

PROMPT_PRESTAZIONE = [
    "Elenca in tre righe i compiti principali di un ordine professionale.",
    "Spiega in un paragrafo che cosa e' un consiglio nazionale di categoria.",
    "Riassumi in due frasi il ruolo della formazione continua per un ingegnere.",
]


# --------------------------------------------------------------------------
# Ollama

def ollama_vivo() -> bool:
    try:
        httpx.get(f"{OLLAMA}/api/tags", timeout=5).raise_for_status()
        return True
    except Exception:
        return False


def modelli_installati() -> set[str]:
    try:
        dati = httpx.get(f"{OLLAMA}/api/tags", timeout=10).json()
        return {m["name"] for m in dati.get("models", [])}
    except Exception:
        return set()


def genera(modello: str, messaggi: list[dict[str, str]], temperatura: float,
           max_token: int, timeout: float = 1800.0) -> dict[str, Any]:
    """Una generazione via API nativa di Ollama.

    Si usa l'API nativa e non quella compatibile OpenAI perche' solo la prima
    restituisce i contatori `eval_count` / `eval_duration`, da cui i token al
    secondo reali. Sono la misura di prestazione che serve alla tesi: un dato
    di throughput sull'hardware vincolato, non una stima da letteratura.
    """
    t0 = time.perf_counter()
    r = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": modello,
            "messages": messaggi,
            "stream": False,
            "options": {"temperature": temperatura, "num_predict": max_token},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    d = r.json()
    durata = time.perf_counter() - t0

    eval_count = d.get("eval_count") or 0
    eval_ns = d.get("eval_duration") or 0
    prompt_count = d.get("prompt_eval_count") or 0
    prompt_ns = d.get("prompt_eval_duration") or 0

    return {
        "risposta": (d.get("message") or {}).get("content", ""),
        "latenza_s": round(durata, 2),
        "token_generati": eval_count,
        "token_prompt": prompt_count,
        "tok_s_generazione": round(eval_count / (eval_ns / 1e9), 2) if eval_ns else None,
        "tok_s_prompt": round(prompt_count / (prompt_ns / 1e9), 2) if prompt_ns else None,
        "caricamento_s": round((d.get("load_duration") or 0) / 1e9, 2),
    }


def memoria_occupata(modello: str) -> str:
    """Legge da `ollama ps` la memoria realmente occupata dal modello caricato."""
    try:
        out = subprocess.check_output(["ollama", "ps"], text=True, timeout=15)
    except Exception:
        return "—"
    for riga in out.splitlines()[1:]:
        campi = riga.split()
        if campi and campi[0].split(":")[0] == modello.split(":")[0]:
            # NAME ID SIZE(2 campi: valore+unita') PROCESSOR ...
            return " ".join(campi[2:4]) if len(campi) >= 4 else "—"
    return "—"


def scarica_modello(modello: str) -> None:
    """Libera la RAM prima di caricare il modello successivo.

    Con 8 GB condivisi due modelli residenti insieme mandano la macchina in
    swap e le latenze misurate diventano quelle del disco, non del modello.
    """
    try:
        subprocess.run(["ollama", "stop", modello], capture_output=True, timeout=30)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Fase A — prestazioni

def fase_prestazioni(modelli: list[str], temperatura: float, max_token: int) -> list[dict[str, Any]]:
    righe = []
    for modello in modelli:
        console.print(f"[cyan]prestazioni[/cyan] {modello}")
        misure, errore = [], None
        for i, p in enumerate(PROMPT_PRESTAZIONE, 1):
            try:
                m = genera(modello, [{"role": "user", "content": p}], temperatura, max_token)
                misure.append(m)
                console.print(f"   {i}/{len(PROMPT_PRESTAZIONE)} "
                              f"{m['tok_s_generazione']} tok/s · {m['latenza_s']}s")
            except Exception as exc:
                errore = f"{type(exc).__name__}: {exc}"
                console.print(f"   [red]fallito: {errore}[/red]")
                break

        ram = memoria_occupata(modello)
        scarica_modello(modello)

        if not misure:
            righe.append({"modello": modello, "errore": errore})
            continue

        tok_s = [m["tok_s_generazione"] for m in misure if m["tok_s_generazione"]]
        righe.append({
            "modello": modello,
            "tok_s_mediana": round(statistics.median(tok_s), 2) if tok_s else None,
            "tok_s_min": min(tok_s) if tok_s else None,
            "tok_s_max": max(tok_s) if tok_s else None,
            "tok_s_prompt_mediana": round(statistics.median(
                [m["tok_s_prompt"] for m in misure if m["tok_s_prompt"]]), 2)
                if any(m["tok_s_prompt"] for m in misure) else None,
            "caricamento_s": misure[0]["caricamento_s"],
            "memoria": ram,
            "licenza": LICENZE.get(modello, "—"),
        })
        console.print()
    return righe


# --------------------------------------------------------------------------
# Fase B — qualita' a contesto congelato

def congela_contesti(items: list[dict], cfg: Config, percorso: Path) -> dict[str, Any]:
    """Esegue il recupero una volta sola e lo salva su disco.

    Se il file esiste gia' viene riusato: cosi' un confronto interrotto puo'
    riprendere senza rifare il retrieval, e soprattutto senza il rischio che
    la seconda meta' dei modelli riceva un contesto diverso dalla prima.
    """
    if percorso.exists():
        with open(percorso, encoding="utf-8") as fh:
            dati = json.load(fh)
        if set(dati.get("contesti", {})) >= {it["id"] for it in items}:
            console.print(f"[dim]contesti riusati da {percorso}[/dim]\n")
            return dati

    motore = Motore()
    contesti: dict[str, Any] = {}
    for it in items:
        _, contesto, categoria = motore.cerca(it["question"], cfg)
        contesti[it["id"]] = {"documenti": contesto, "categoria": categoria}
        console.print(f"[dim]{it['id']} · {len(contesto)} documenti · categoria {categoria}[/dim]")

    dati = {
        "creato": datetime.now().isoformat(timespec="seconds"),
        "configurazione_retrieval": cfg.descrizione(),
        "contesti": contesti,
    }
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False)
    console.print(f"[green]contesti congelati in {percorso}[/green]\n")
    return dati


def fase_qualita(modelli: list[str], items: list[dict], contesti: dict[str, Any],
                 temperatura: float, max_token: int, checkpoint: Path) -> list[dict[str, Any]]:
    fatte: dict[str, list[dict]] = {}
    if checkpoint.exists():
        with open(checkpoint, encoding="utf-8") as fh:
            fatte = json.load(fh)
        console.print(f"[yellow]ripresa: {sum(len(v) for v in fatte.values())} "
                      f"generazioni gia' fatte[/yellow]\n")

    for modello in modelli:
        gia = {r["id"] for r in fatte.get(modello, [])}
        rimaste = [it for it in items if it["id"] not in gia]
        if not rimaste:
            continue
        console.print(f"[bold cyan]{modello}[/bold cyan] — {len(rimaste)} domande")

        for it in rimaste:
            documenti = contesti[it["id"]]["documenti"]
            messaggi = PromptBuilder.build_prompt(it["question"], documenti)
            try:
                g = genera(modello, messaggi, temperatura, max_token)
            except Exception as exc:
                console.print(f"  [red]{it['id']} fallita: {type(exc).__name__}: {exc}[/red]")
                continue

            must = it.get("must_contain", [])
            colpi = [t for t in must if t.lower() in g["risposta"].lower()]
            passata = (len(colpi) == len(must)) if must else None

            fatte.setdefault(modello, []).append({
                "id": it["id"],
                "domanda": it["question"],
                "risposta": g["risposta"],
                "must_contain": must,
                "must_contain_colpiti": colpi,
                "must_contain_passata": passata,
                "latenza_s": g["latenza_s"],
                "token_generati": g["token_generati"],
                "token_prompt": g["token_prompt"],
                "tok_s_generazione": g["tok_s_generazione"],
            })

            simbolo = "[green]✓[/green]" if passata else "[red]✗[/red]"
            console.print(f"  {simbolo} {it['id']} · {g['latenza_s']}s · "
                          f"{g['token_generati']} token · {g['tok_s_generazione']} tok/s")

            with open(checkpoint, "w", encoding="utf-8") as fh:
                json.dump(fatte, fh, ensure_ascii=False)

        scarica_modello(modello)
        console.print()

    risultati = []
    for modello in modelli:
        righe = fatte.get(modello, [])
        if not righe:
            continue
        passate = [1 if r["must_contain_passata"] else 0
                   for r in righe if r["must_contain_passata"] is not None]
        latenze = [r["latenza_s"] for r in righe]
        tok = [r["tok_s_generazione"] for r in righe if r["tok_s_generazione"]]

        # `format_ci` vuole un riepilogo con mean/ci_low/ci_high, non la coppia
        # grezza restituita da `wilson_ci`.
        ci = None
        if passate:
            lo, hi = S.wilson_ci(sum(passate), len(passate))
            ci = {"mean": sum(passate) / len(passate), "ci_low": lo, "ci_high": hi}

        risultati.append({
            "modello": modello,
            "domande": len(righe),
            "must_contain_pass": sum(passate) / len(passate) if passate else None,
            "must_contain_ci": ci,
            "latenza_mediana_s": round(statistics.median(latenze), 1) if latenze else None,
            "tok_s_mediana": round(statistics.median(tok), 2) if tok else None,
            "token_generati_mediana": round(statistics.median(
                [r["token_generati"] for r in righe])) if righe else None,
            "licenza": LICENZE.get(modello, "—"),
            "dettaglio": righe,
        })
    return risultati


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Confronto fra generatori locali a contesto congelato")
    ap.add_argument("--dataset", default="config/golden_dataset_v2.json")
    ap.add_argument("--models", nargs="*", default=MODELLI_DEFAULT)
    ap.add_argument("--limit", type=int, default=None,
                    help="numero di domande per la fase di qualita' (su CPU conviene 10-15)")
    ap.add_argument("--max-token", type=int, default=None,
                    help="tetto ai token generati; default: llm.max_tokens del YAML")
    ap.add_argument("--solo-prestazioni", action="store_true",
                    help="esegue solo la fase A: token/s, caricamento, memoria")
    ap.add_argument("--contesti", default="results/contesti_congelati.json")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if not ollama_vivo():
        console.print(f"[red]Ollama non risponde su {OLLAMA}.[/red] Avvialo con: ollama serve")
        sys.exit(1)

    installati = modelli_installati()
    mancanti = [m for m in args.models
                if m not in installati and f"{m}:latest" not in installati]
    if mancanti:
        console.print("[red]Modelli non installati:[/red] " + ", ".join(mancanti))
        for m in mancanti:
            console.print(f"  ollama pull {m}")
        console.print("[dim]Circa 2 GB ciascuno. Dopo il confronto si liberano con "
                      "`ollama rm <modello>`.[/dim]")
        sys.exit(1)

    rag = ConfigLoader.get_rag_config()
    llm = rag.get("llm", {})
    temperatura = llm.get("temperature", 0.2)
    max_token = args.max_token or llm.get("max_tokens", 2048)

    console.print("\n[bold cyan]Confronto fra generatori locali[/bold cyan]")
    console.print(f"modelli: {', '.join(args.models)}")
    console.print(f"temperatura={temperatura} · max_token={max_token}\n")

    prestazioni = fase_prestazioni(args.models, temperatura, max_token)

    t = Table(title="Fase A — prestazioni sull'hardware reale", title_style="bold")
    for c in ("modello", "tok/s (mediana)", "intervallo", "caricamento", "memoria", "licenza"):
        t.add_column(c)
    for r in prestazioni:
        if r.get("errore"):
            t.add_row(r["modello"], "[red]errore[/red]", r["errore"][:30], "—", "—", "—")
            continue
        t.add_row(r["modello"], str(r["tok_s_mediana"]),
                  f"{r['tok_s_min']}–{r['tok_s_max']}",
                  f"{r['caricamento_s']}s", r["memoria"], r["licenza"])
    console.print(t)
    console.print()

    qualita: list[dict[str, Any]] = []
    if not args.solo_prestazioni:
        with open(args.dataset, encoding="utf-8") as fh:
            items = json.load(fh)["items"]
        if args.limit:
            items = items[: args.limit]

        ret = rag.get("retrieval", {})
        rer = rag.get("reranking", {})
        cfg = Config(
            nome="produzione",
            top_k=ret.get("top_k", 25),
            reranker=rer.get("model") if rer.get("enabled", True) else None,
            rerank_top_k=rer.get("top_k", 5),
            filtro_categoria=ret.get("category_filter", True),
            score_threshold=ret.get("score_threshold", 0.3),
        )
        console.print(f"[dim]retrieval: {cfg.descrizione()}[/dim]")

        dati_ctx = congela_contesti(items, cfg, Path(args.contesti))
        qualita = fase_qualita(args.models, items, dati_ctx["contesti"], temperatura, max_token,
                               RESULTS_DIR / "compare_generators.checkpoint.json")

        t = Table(title=f"Fase B — qualita' a contesto congelato (n={len(items)}, IC 95%)",
                  title_style="bold")
        for c in ("modello", "must-contain", "latenza mediana", "tok/s", "token generati", "licenza"):
            t.add_column(c)
        for r in qualita:
            ci = S.format_ci(r["must_contain_ci"], pct=True) if r["must_contain_ci"] else "—"
            t.add_row(r["modello"], ci,
                      f"{r['latenza_mediana_s']}s", str(r["tok_s_mediana"]),
                      str(r["token_generati_mediana"]), r["licenza"])
        console.print(t)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    percorso = RESULTS_DIR / f"generators_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    with open(percorso, "w", encoding="utf-8") as fh:
        json.dump({
            "data": datetime.now().isoformat(timespec="seconds"),
            "modelli": args.models,
            "parametri": {"temperatura": temperatura, "max_token": max_token,
                          "domande": args.limit, "dataset": args.dataset},
            "ambiente": S.describe_environment(),
            "prestazioni": prestazioni,
            "qualita": qualita,
            "nota": ("Contesto congelato: il recupero e' stato eseguito una volta sola con la "
                     "configurazione di produzione e gli stessi documenti sono stati passati a "
                     "tutti i modelli. Le differenze sono quindi attribuibili al solo generatore."),
        }, fh, ensure_ascii=False, indent=2)
    console.print(f"\n[green]Risultati:[/green] {percorso}")

    if args.markdown:
        console.print("\n[bold]Tabella per la tesi[/bold]\n")
        print("| Modello | tok/s | Memoria | Licenza | must-contain |")
        print("|---|---|---|---|---|")
        q = {r["modello"]: r for r in qualita}
        for r in prestazioni:
            if r.get("errore"):
                continue
            mc = q.get(r["modello"], {}).get("must_contain_pass")
            print(f"| {r['modello']} | {r['tok_s_mediana']} | {r['memoria']} | "
                  f"{r['licenza']} | {f'{100*mc:.1f}%' if mc is not None else '—'} |")


if __name__ == "__main__":
    main()
