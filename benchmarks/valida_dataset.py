#!/usr/bin/env python3
"""
Controlla che un dataset di valutazione sia utilizzabile *prima* di lanciare il run.

Perche' serve
-------------
Un run completo costa ore. Un `must_contain` vuoto, un `expected_sources`
dimenticato o un id duplicato non fanno fallire lo script: producono
silenziosamente metriche prive di senso (una domanda senza fonte attesa ha
Recall indefinito, una senza `must_contain` risulta sempre superata). Meglio
scoprirlo in due secondi che dopo quattro ore.

Il controllo sulla sovrapposizione
----------------------------------
Con `--confronta-con` il file viene confrontato con il dataset usato per
scegliere la configurazione. Un insieme di controllo ha senso solo se le sue
domande sono davvero nuove: se una e' la riformulazione di una gia' vista, la
stima di generalizzazione e' ottimistica. Il confronto e' lessicale
(`difflib`), quindi individua le riformulazioni evidenti, non le equivalenze
semantiche: e' un aiuto, non un giudice.

Uso:
    python benchmarks/valida_dataset.py config/holdout_v1.json \
        --confronta-con config/golden_dataset_v2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()

CAMPI_OBBLIGATORI = ("id", "question", "category", "reference_answer",
                     "expected_sources", "must_contain")
SOGLIA_SOMIGLIANZA = 0.75


def normalizza(testo: str) -> str:
    return " ".join(testo.lower().split())


def carica(percorso: str) -> list[dict]:
    with open(percorso, encoding="utf-8") as fh:
        dati = json.load(fh)
    return dati["items"] if isinstance(dati, dict) else dati


def controlla(items: list[dict]) -> tuple[list[str], list[str]]:
    errori: list[str] = []
    avvisi: list[str] = []
    visti: set[str] = set()

    for i, it in enumerate(items):
        etichetta = it.get("id") or f"#{i}"

        for campo in CAMPI_OBBLIGATORI:
            if campo not in it:
                errori.append(f"{etichetta}: manca il campo '{campo}'")

        ident = it.get("id", "")
        if not ident:
            errori.append(f"#{i}: id vuoto")
        elif ident in visti:
            errori.append(f"{etichetta}: id duplicato")
        else:
            visti.add(ident)

        domanda = (it.get("question") or "").strip()
        if not domanda:
            errori.append(f"{etichetta}: domanda vuota")
        elif len(domanda) < 12:
            avvisi.append(f"{etichetta}: domanda molto corta ({len(domanda)} caratteri)")

        if not (it.get("reference_answer") or "").strip():
            errori.append(f"{etichetta}: reference_answer vuota — senza non c'e' giudizio possibile")

        fonti = it.get("expected_sources") or []
        if not fonti:
            errori.append(f"{etichetta}: expected_sources vuoto — Hit@k e Recall@k sarebbero indefiniti")
        for f in fonti:
            if f.startswith("http"):
                avvisi.append(f"{etichetta}: fonte '{f}' e' un URL completo; "
                              f"il confronto e' su frammenti (es. 'cni/consiglio')")

        termini = it.get("must_contain") or []
        if not termini:
            errori.append(f"{etichetta}: must_contain vuoto — la domanda risulterebbe sempre superata")

        # Coerenza interna: cio' che si pretende nella risposta deve comparire
        # nella risposta di riferimento, altrimenti il criterio e' irraggiungibile.
        riferimento = normalizza(it.get("reference_answer") or "")
        for t in termini:
            if t and normalizza(t) not in riferimento:
                errori.append(f"{etichetta}: il termine richiesto '{t}' non compare "
                              f"nella reference_answer — criterio impossibile da soddisfare")

    return errori, avvisi


def sovrapposizione(nuovi: list[dict], vecchi: list[dict]) -> list[tuple[str, str, float, str]]:
    trovati = []
    for n in nuovi:
        dn = normalizza(n.get("question") or "")
        if not dn:
            continue
        migliore, punteggio = None, 0.0
        for v in vecchi:
            s = SequenceMatcher(None, dn, normalizza(v.get("question") or "")).ratio()
            if s > punteggio:
                migliore, punteggio = v, s
        if punteggio >= SOGLIA_SOMIGLIANZA and migliore:
            trovati.append((n.get("id", "?"), migliore.get("id", "?"), punteggio,
                            migliore.get("question", "")))
    return trovati


def main() -> None:
    ap = argparse.ArgumentParser(description="Valida un dataset di valutazione prima del run")
    ap.add_argument("dataset")
    ap.add_argument("--confronta-con", default=None,
                    help="dataset di riferimento per rilevare domande sovrapposte")
    args = ap.parse_args()

    items = carica(args.dataset)
    console.print(f"\n[bold cyan]Validazione[/bold cyan]  {args.dataset}  —  {len(items)} domande\n")

    errori, avvisi = controlla(items)

    if args.confronta_con:
        vecchi = carica(args.confronta_con)
        simili = sovrapposizione(items, vecchi)
        if simili:
            t = Table(title="Domande troppo simili al dataset di riferimento", title_style="bold yellow")
            t.add_column("nuova"); t.add_column("simile a"); t.add_column("somiglianza", justify="right")
            t.add_column("testo di riferimento", overflow="fold")
            for a, b, s, testo in simili:
                t.add_row(a, b, f"{s:.0%}", testo)
            console.print(t)
            avvisi.append(f"{len(simili)} domande somigliano a domande gia' usate: "
                          f"riscrivile o accetta che la stima sia ottimistica")
        else:
            console.print("[green]Nessuna sovrapposizione lessicale con il dataset di riferimento.[/green]")

    if avvisi:
        console.print("\n[yellow]Avvisi[/yellow]")
        for a in avvisi:
            console.print(f"  [yellow]·[/yellow] {a}")

    if errori:
        console.print("\n[bold red]Errori bloccanti[/bold red]")
        for e in errori:
            console.print(f"  [red]·[/red] {e}")
        console.print(f"\n[bold red]{len(errori)} errori: non lanciare il run.[/bold red]\n")
        sys.exit(1)

    console.print(f"\n[bold green]Dataset valido.[/bold green] {len(items)} domande, "
                  f"{len(avvisi)} avvisi non bloccanti.\n")


if __name__ == "__main__":
    main()
