#!/usr/bin/env python3
"""
Layer statistico per la valutazione del sistema RAG CNI.

Perche' serve
-------------
Riportare "correctness media = 3.2" su 30 domande non e' un risultato: senza
una misura della dispersione non si sa se 3.2 sia distinguibile da 2.8. E
confrontare due configurazioni guardando due medie non dice se la differenza
sia reale o rumore campionario.

Questo modulo fornisce i due strumenti minimi per un capitolo sperimentale
difendibile:

  1. INTERVALLI DI CONFIDENZA su ogni valore riportato
  2. TEST APPAIATI per confrontare due configurazioni

Campioni appaiati
-----------------
Punto metodologico decisivo. Quando si confrontano due configurazioni (es.
reranker acceso/spento) le si valuta sulle STESSE domande. Le osservazioni
sono quindi accoppiate, e i test appaiati vanno usati al posto di quelli per
campioni indipendenti: eliminano la variabilita' dovuta al fatto che alcune
domande sono intrinsecamente piu' difficili di altre, e hanno molta piu'
potenza statistica a parita' di numerosita' — cosa che conta parecchio con
n = 30.

Quale test usare
----------------
  punteggi ordinali (giudizi 0-5, MRR, nDCG)  ->  wilcoxon_signed_rank
  esiti binari (Hit@k, must_contain, pass)    ->  mcnemar
  proporzioni singole (fallback rate, Hit@k)  ->  wilson_ci
  qualunque media                             ->  bootstrap_ci
  dimensione dell'effetto                     ->  cliffs_delta

Riproducibilita'
----------------
Il bootstrap e' stocastico: il seme e' fissato (DEFAULT_SEED) in modo che gli
stessi dati producano sempre gli stessi intervalli. I valori riportati in
tesi devono essere riproducibili da chi legge.

scipy e' usato quando disponibile (implementazioni di riferimento, citabili);
in sua assenza il modulo ricade su implementazioni interne equivalenti, cosi'
il codice gira comunque.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence

try:  # pragma: no cover - dipende dall'ambiente
    from scipy import stats as _scipy_stats
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover
    _scipy_stats = None
    HAVE_SCIPY = False

DEFAULT_SEED = 20260824
DEFAULT_RESAMPLES = 10_000
DEFAULT_ALPHA = 0.05


# ---------------------------------------------------------------------------
# Statistiche descrittive
# ---------------------------------------------------------------------------

def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    """Deviazione standard campionaria (denominatore n-1)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# ---------------------------------------------------------------------------
# Intervalli di confidenza
# ---------------------------------------------------------------------------

def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = mean,
    n_resamples: int = DEFAULT_RESAMPLES,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """Intervallo di confidenza bootstrap con metodo dei percentili.

    Non assume normalita' — cosa opportuna con n = 30 e punteggi ordinali su
    scala 0-5, dove l'assunzione gaussiana e' difficile da giustificare.
    """
    vals = list(values)
    if len(vals) < 2:
        point = statistic(vals) if vals else 0.0
        return (point, point)

    rng = random.Random(seed)
    n = len(vals)
    replicates = []
    for _ in range(n_resamples):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        replicates.append(statistic(sample))
    replicates.sort()

    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)
    return (replicates[lo_idx], replicates[hi_idx])


def wilson_ci(successes: int, n: int, alpha: float = DEFAULT_ALPHA) -> tuple[float, float]:
    """Intervallo di Wilson per una proporzione.

    Preferito all'intervallo normale (Wald) perche' resta dentro [0, 1] e non
    degenera quando la proporzione e' vicina a 0 o 1 — situazione frequente
    qui (fallback rate = 0.0, Hit@k = 1.0 su alcune categorie).
    """
    if n == 0:
        return (0.0, 0.0)
    z = _z_critical(alpha)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _z_critical(alpha: float) -> float:
    if HAVE_SCIPY:
        return float(_scipy_stats.norm.ppf(1 - alpha / 2))
    return {0.10: 1.6449, 0.05: 1.9600, 0.01: 2.5758}.get(round(alpha, 2), 1.9600)


def summarize_metric(
    values: Sequence[float],
    name: str = "",
    binary: bool = False,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Riepilogo pronto da riportare in tabella: media, IC 95%, dispersione.

    `binary=True` per metriche 0/1 (Hit@k, pass/fail): usa l'intervallo di
    Wilson, piu' appropriato del bootstrap per le proporzioni.
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return {"name": name, "n": 0, "mean": None, "ci_low": None, "ci_high": None}

    m = mean(vals)
    if binary:
        lo, hi = wilson_ci(int(round(sum(vals))), n, alpha)
        method = "wilson"
    else:
        lo, hi = bootstrap_ci(vals, alpha=alpha)
        method = "bootstrap_percentile"

    return {
        "name": name,
        "n": n,
        "mean": round(m, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "ci_method": method,
        "sd": round(stdev(vals), 4),
        "median": round(median(vals), 4),
    }


def format_ci(summary: dict[str, Any], pct: bool = False) -> str:
    """Rende un riepilogo nella forma da tabella: 3.40 [2.81, 3.95]."""
    if summary.get("mean") is None:
        return "—"
    scale, suffix = (100, "%") if pct else (1, "")
    fmt = "{:.1f}" if pct else "{:.3f}"
    return (
        f"{fmt.format(summary['mean'] * scale)}{suffix} "
        f"[{fmt.format(summary['ci_low'] * scale)}{suffix}, "
        f"{fmt.format(summary['ci_high'] * scale)}{suffix}]"
    )


# ---------------------------------------------------------------------------
# Test appaiati
# ---------------------------------------------------------------------------

def wilcoxon_signed_rank(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """Test di Wilcoxon dei ranghi con segno, per campioni appaiati.

    Alternativa non parametrica al t-test appaiato: appropriata per punteggi
    ordinali (i giudizi 0-5) dove la distanza fra 3 e 4 non e' necessariamente
    uguale a quella fra 4 e 5.

    H0: la distribuzione delle differenze e' simmetrica attorno a zero.
    """
    pairs = [(float(x), float(y)) for x, y in zip(a, b)]
    diffs = [y - x for x, y in pairs if y != x]
    n_eff = len(diffs)

    if n_eff == 0:
        return {"test": "wilcoxon", "n_pairs": len(pairs), "n_nonzero": 0,
                "statistic": None, "p_value": 1.0, "note": "nessuna differenza fra le due condizioni"}

    if HAVE_SCIPY and n_eff >= 1:
        try:
            res = _scipy_stats.wilcoxon([x for x, _ in pairs], [y for _, y in pairs])
            stat, p = float(res.statistic), float(res.pvalue)
        except ValueError:
            stat, p = _wilcoxon_fallback(diffs)
    else:
        stat, p = _wilcoxon_fallback(diffs)

    return {
        "test": "wilcoxon",
        "n_pairs": len(pairs),
        "n_nonzero": n_eff,
        "statistic": round(stat, 4) if stat is not None else None,
        "p_value": round(p, 5),
        "significant_05": p < 0.05,
    }


def _wilcoxon_fallback(diffs: Sequence[float]) -> tuple[float, float]:
    """Approssimazione normale con correzione per i ranghi ex aequo."""
    n = len(diffs)
    ordered = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(diffs[ordered[j + 1]]) == abs(diffs[ordered[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for idx in range(i, j + 1):
            ranks[ordered[idx]] = avg
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, diffs) if d < 0)
    stat = min(w_plus, w_minus)

    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma == 0:
        return stat, 1.0
    z = (stat - mu + 0.5) / sigma
    p = 2 * _norm_cdf(-abs(z))
    return stat, min(1.0, p)


def mcnemar(a: Sequence[int], b: Sequence[int]) -> dict[str, Any]:
    """Test di McNemar per esiti binari appaiati (Hit@k, pass/fail).

    Guarda solo le domande in cui le due configurazioni sono in disaccordo:
      b01 = la configurazione A fallisce, B riesce
      b10 = A riesce, B fallisce
    Le domande su cui entrambe si comportano allo stesso modo non portano
    informazione sulla differenza.

    Usa il test binomiale esatto: obbligatorio con n piccolo, dove
    l'approssimazione chi-quadro non e' affidabile.
    """
    b01 = sum(1 for x, y in zip(a, b) if not x and y)
    b10 = sum(1 for x, y in zip(a, b) if x and not y)
    n_disc = b01 + b10

    if n_disc == 0:
        return {"test": "mcnemar_exact", "n_pairs": len(list(a)), "b01": 0, "b10": 0,
                "p_value": 1.0, "significant_05": False,
                "note": "nessun disaccordo fra le due condizioni"}

    p = min(1.0, 2 * sum(math.comb(n_disc, i) for i in range(min(b01, b10) + 1)) / (2 ** n_disc))

    return {
        "test": "mcnemar_exact",
        "n_pairs": len(list(a)),
        "b01_only_b_succeeds": b01,
        "b10_only_a_succeeds": b10,
        "n_discordant": n_disc,
        "p_value": round(p, 5),
        "significant_05": p < 0.05,
    }


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """Delta di Cliff: dimensione dell'effetto non parametrica.

    Un p-value dice se una differenza sia distinguibile dal rumore, non se sia
    grande abbastanza da avere importanza pratica. Entrambi vanno riportati.

    delta = P(b > a) - P(a > b), in [-1, 1]. Soglie convenzionali
    (Romano et al., 2006): |d| < 0.147 trascurabile, < 0.33 piccolo,
    < 0.474 medio, oltre grande.
    """
    xs, ys = [float(v) for v in a], [float(v) for v in b]
    if not xs or not ys:
        return {"delta": 0.0, "magnitude": "indeterminata"}

    greater = sum(1 for x in xs for y in ys if y > x)
    lesser = sum(1 for x in xs for y in ys if y < x)
    delta = (greater - lesser) / (len(xs) * len(ys))

    a_delta = abs(delta)
    if a_delta < 0.147:
        magnitude = "trascurabile"
    elif a_delta < 0.33:
        magnitude = "piccola"
    elif a_delta < 0.474:
        magnitude = "media"
    else:
        magnitude = "grande"

    return {"delta": round(delta, 4), "magnitude": magnitude}


def paired_report(
    a: Sequence[float],
    b: Sequence[float],
    name: str = "",
    binary: bool = False,
    label_a: str = "A",
    label_b: str = "B",
) -> dict[str, Any]:
    """Confronto completo fra due configurazioni su una metrica.

    Restituisce medie con IC di entrambe, differenza con IC bootstrap sulle
    differenze appaiate, test appropriato e dimensione dell'effetto: tutto
    quello che serve per una riga della tabella comparativa.
    """
    xs, ys = [float(v) for v in a], [float(v) for v in b]
    diffs = [y - x for x, y in zip(xs, ys)]

    report: dict[str, Any] = {
        "metric": name,
        "label_a": label_a,
        "label_b": label_b,
        label_a: summarize_metric(xs, name, binary=binary),
        label_b: summarize_metric(ys, name, binary=binary),
        "mean_difference": round(mean(diffs), 4),
        "effect_size": cliffs_delta(xs, ys),
    }

    if len(diffs) >= 2:
        lo, hi = bootstrap_ci(diffs)
        report["difference_ci"] = [round(lo, 4), round(hi, 4)]

    report["significance"] = (
        mcnemar([int(round(v)) for v in xs], [int(round(v)) for v in ys])
        if binary else wilcoxon_signed_rank(xs, ys)
    )
    return report


# ---------------------------------------------------------------------------
# Utilita'
# ---------------------------------------------------------------------------

def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def describe_environment() -> dict[str, Any]:
    """Da salvare nei run: quale implementazione ha prodotto i numeri."""
    return {
        "scipy_available": HAVE_SCIPY,
        "bootstrap_resamples": DEFAULT_RESAMPLES,
        "seed": DEFAULT_SEED,
        "alpha": DEFAULT_ALPHA,
    }
