#!/usr/bin/env python3
"""
Accordo fra giudizio umano e giudizio automatico.

Perche' e' il modulo piu' importante della valutazione
------------------------------------------------------
Un LLM-as-judge e' uno strumento di misura, e ogni strumento di misura ha un
errore. Riportare punteggi qualitativi senza aver dimostrato che il giudice
concorda con un valutatore umano equivale a pesare senza aver tarato la
bilancia.

Nel caso di questo progetto la questione e' particolarmente acuta: il giudice
e' lo stesso modello che genera le risposte (qwen2.5:3b), quindi somma due
bias noti in letteratura — self-preference e capacita' insufficiente.

Con 30 domande x 3 metriche = 90 giudizi, l'annotazione umana e' fattibile in
poche ore ed e' il gold standard. Il giudice automatico diventa allora
OGGETTO di studio invece che strumento: la domanda si ribalta in «un modello
eseguibile sotto questo vincolo hardware puo' sostituire il giudizio umano?».
Qualunque sia la risposta, e' un risultato riportabile.

Le misure prodotte
------------------
  kappa di Cohen con pesi quadratici
      La misura corretta per scale ORDINALI: uno scarto di 1 punto pesa meno
      di uno scarto di 4. Corregge inoltre per l'accordo dovuto al caso, cosa
      che la percentuale di accordo grezza non fa.
      Interpretazione convenzionale (Landis & Koch, 1977):
        < 0.00 nessun accordo · 0.01-0.20 lieve · 0.21-0.40 discreto
        0.41-0.60 moderato · 0.61-0.80 sostanziale · 0.81-1.00 quasi perfetto

  alfa di Krippendorff (metrica ordinale)
      Piu' robusto di kappa con celle vuote e sbilanciamenti, situazione
      normale con n piccolo. Convenzione: >= 0.800 affidabile, 0.667-0.800
      accettabile solo per conclusioni provvisorie, sotto 0.667 inaffidabile.

  MAE, accordo esatto, accordo entro 1 punto
      Descrittivi, immediati da leggere, ma NON corretti per il caso: da
      riportare accanto a kappa, mai al suo posto.

  correlazione di Pearson
      Dice se i due valutatori ordinano allo stesso modo, non se concordano
      sui valori: due giudici che differiscono sistematicamente di 2 punti
      hanno r = 1 e accordo pessimo. Riportata per completezza.

  matrice di confusione
      6x6 sui voti 0-5. E' cio' che rende visibile la NATURA del disaccordo:
      un giudice che sbaglia in modo sistematico (sempre piu' severo) e' un
      problema diverso da uno che sbaglia in modo casuale.

Usage (come modulo):
    from benchmarks.agreement import agreement_report
    rep = agreement_report(voti_umani, voti_giudice)
"""
from __future__ import annotations

import math
from typing import Any, Sequence

SCALA = list(range(6))  # voti 0-5

LANDIS_KOCH = [
    (0.81, "quasi perfetto"),
    (0.61, "sostanziale"),
    (0.41, "moderato"),
    (0.21, "discreto"),
    (0.01, "lieve"),
    (-1.01, "nessun accordo"),
]


def interpreta_kappa(k: float) -> str:
    if k != k:  # NaN
        return "non calcolabile"
    for soglia, etichetta in LANDIS_KOCH:
        if k >= soglia:
            return etichetta
    return "nessun accordo"


def interpreta_alpha(a: float) -> str:
    if a != a:
        return "non calcolabile"
    if a >= 0.800:
        return "affidabile"
    if a >= 0.667:
        return "accettabile solo per conclusioni provvisorie"
    return "inaffidabile"


# ---------------------------------------------------------------------------

def matrice_confusione(umani: Sequence[int], giudice: Sequence[int]) -> list[list[int]]:
    """Righe = voto umano, colonne = voto del giudice."""
    m = [[0] * len(SCALA) for _ in SCALA]
    for u, g in zip(umani, giudice):
        if u in SCALA and g in SCALA:
            m[u][g] += 1
    return m


def kappa_pesato(umani: Sequence[int], giudice: Sequence[int], pesi: str = "quadratic") -> float:
    """Kappa di Cohen con pesi lineari o quadratici.

    Con pesi quadratici il disaccordo e' penalizzato in proporzione al
    quadrato della distanza fra i voti: e' la scelta standard per le scale
    ordinali come una valutazione 0-5.
    """
    n = len(umani)
    if n == 0:
        return float("nan")

    k = len(SCALA)
    obs = matrice_confusione(umani, giudice)

    riga = [sum(obs[i]) for i in range(k)]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    # matrice attesa per indipendenza
    att = [[riga[i] * col[j] / n for j in range(k)] for i in range(k)]

    denom_peso = (k - 1) ** 2 if pesi == "quadratic" else (k - 1)

    def w(i: int, j: int) -> float:
        d = abs(i - j)
        return (d * d if pesi == "quadratic" else d) / denom_peso

    num = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w(i, j) * att[i][j] for i in range(k) for j in range(k))

    if den == 0:
        # nessun disaccordo atteso: accordo perfetto se non ce n'e' di osservato
        return 1.0 if num == 0 else float("nan")
    return 1 - num / den


def krippendorff_alpha(umani: Sequence[int], giudice: Sequence[int]) -> float:
    """Alfa di Krippendorff con metrica di differenza ordinale (qui: intervallo).

    Implementazione diretta per due valutatori senza dati mancanti, che e' il
    caso di questo progetto.
    """
    coppie = [(u, g) for u, g in zip(umani, giudice) if u is not None and g is not None]
    n = len(coppie)
    if n < 2:
        return float("nan")

    # disaccordo osservato: media dei quadrati delle differenze entro unita'
    Do = sum((u - g) ** 2 for u, g in coppie) / n

    # disaccordo atteso: media dei quadrati su tutte le coppie possibili
    tutti = [v for coppia in coppie for v in coppia]
    N = len(tutti)
    De = sum((tutti[i] - tutti[j]) ** 2 for i in range(N) for j in range(N) if i != j) / (N * (N - 1))

    if De == 0:
        return 1.0 if Do == 0 else float("nan")
    return 1 - Do / De


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
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


# ---------------------------------------------------------------------------

def agreement_report(umani: Sequence[Any], giudice: Sequence[Any]) -> dict[str, Any]:
    """Report completo per una singola metrica.

    Le coppie con un voto mancante (None) o fuori scala vengono escluse, e il
    numero effettivo di coppie usate e' riportato: non va mai nascosto.
    """
    coppie = [
        (int(u), int(g)) for u, g in zip(umani, giudice)
        if u is not None and g is not None and int(u) in SCALA and int(g) in SCALA
    ]
    n = len(coppie)
    if n == 0:
        return {"n": 0, "disponibile": False,
                "nota": "nessuna coppia di voti valida: annotazione non ancora eseguita"}

    u = [c[0] for c in coppie]
    g = [c[1] for c in coppie]
    diff = [abs(a - b) for a, b in coppie]
    scarti = [b - a for a, b in coppie]  # giudice meno umano

    k_quad = kappa_pesato(u, g, "quadratic")
    k_lin = kappa_pesato(u, g, "linear")
    alpha = krippendorff_alpha(u, g)
    bias = sum(scarti) / n

    return {
        "disponibile": True,
        "n": n,
        "media_umano": round(sum(u) / n, 3),
        "media_giudice": round(sum(g) / n, 3),
        "bias_giudice": round(bias, 3),
        "direzione_bias": ("il giudice e' piu' generoso dell'umano" if bias > 0.25
                           else "il giudice e' piu' severo dell'umano" if bias < -0.25
                           else "nessun bias sistematico rilevante"),
        "mae": round(sum(diff) / n, 3),
        "accordo_esatto": round(sum(1 for d in diff if d == 0) / n, 3),
        "accordo_entro_1": round(sum(1 for d in diff if d <= 1) / n, 3),
        "kappa_quadratico": None if k_quad != k_quad else round(k_quad, 3),
        "kappa_lineare": None if k_lin != k_lin else round(k_lin, 3),
        "interpretazione_kappa": interpreta_kappa(k_quad),
        "krippendorff_alpha": None if alpha != alpha else round(alpha, 3),
        "interpretazione_alpha": interpreta_alpha(alpha),
        "pearson_r": None if (r := pearson(u, g)) != r else round(r, 3),
        "matrice_confusione": matrice_confusione(u, g),
        "scala": SCALA,
    }


def report_completo(
    annotazioni: dict[str, dict[str, Any]],
    giudizi: dict[str, dict[str, Any]],
    metriche: Sequence[str] = ("faithfulness", "answer_relevance", "correctness"),
) -> dict[str, Any]:
    """Accordo su tutte le metriche.

    `annotazioni`: {question_id: {metrica: voto}}
    `giudizi`:     {question_id: {metrica: voto}}
    Vengono usate solo le domande presenti in entrambi.
    """
    comuni = sorted(set(annotazioni) & set(giudizi))
    out: dict[str, Any] = {
        "n_domande_annotate": len(annotazioni),
        "n_domande_con_giudizio": len(giudizi),
        "n_domande_confrontabili": len(comuni),
        "metriche": {},
    }

    validi = []
    for m in metriche:
        u = [annotazioni[q].get(m) for q in comuni]
        g = [giudizi[q].get(m) for q in comuni]
        rep = agreement_report(u, g)
        out["metriche"][m] = rep
        if rep.get("disponibile") and rep.get("kappa_quadratico") is not None:
            validi.append(rep["kappa_quadratico"])

    if validi:
        medio = sum(validi) / len(validi)
        out["kappa_medio"] = round(medio, 3)
        out["interpretazione_complessiva"] = interpreta_kappa(medio)
        out["giudice_utilizzabile"] = medio >= 0.61
        out["conclusione"] = (
            "L'accordo con il giudizio umano e' sufficiente: i punteggi automatici "
            "possono essere riportati, dichiarando kappa."
            if medio >= 0.61 else
            "L'accordo con il giudizio umano NON e' sufficiente: i punteggi automatici "
            "non vanno riportati come risultati. L'insufficienza e' essa stessa un "
            "risultato, da documentare."
        )
    else:
        out["kappa_medio"] = None
        out["giudice_utilizzabile"] = None
        out["conclusione"] = "Annotazione umana non ancora disponibile."

    return out
