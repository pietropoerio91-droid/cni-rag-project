"""Peso alla recenza fra i documenti pertinenti.

Si applica dopo il reranker, sui candidati che il reranker ha gia' valutato
(di norma 25), prima di tenere i migliori `top_k`:

    finale = (1 - w) * pertinenza + w * recenza

- pertinenza: punteggio del reranker riportato in [0, 1] con min-max sui candidati;
- recenza: data del documento riportata in [0, 1] sui soli candidati datati
  (il piu' vecchio vale 0, il piu' recente 1). Se tutti hanno la stessa data, vale 1;
- documenti senza data: recenza neutra (`neutral`, di default 0,5), cosi' non sono
  ne' premiati ne' penalizzati;
- `w` = `reranking.recency_weight`. Con 0 l'ordine e' esattamente quello del reranker.

La recenza e' relativa ai candidati della domanda, non alla data di oggi: tra due
documenti che parlano della stessa cosa vince il piu' recente, senza dover
stabilire se la domanda sia "temporale". Con un peso piccolo la pertinenza resta
dominante e la data decide soprattutto fra documenti di pertinenza simile.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _ordinale(valore: Any) -> int | None:
    if not valore:
        return None
    try:
        return date.fromisoformat(str(valore)[:10]).toordinal()
    except ValueError:
        return None


def _minmax(valori: list[float]) -> list[float]:
    lo, hi = min(valori), max(valori)
    if hi == lo:
        return [1.0] * len(valori)
    return [(v - lo) / (hi - lo) for v in valori]


def apply_recency(results: list[dict[str, Any]], weight: float, score_key: str = "rerank_score",
                  date_key: str = "date", neutral: float = 0.5) -> list[dict[str, Any]]:
    """Riordina `results` combinando pertinenza e recenza; con `weight` <= 0 li lascia invariati.

    Aggiunge a ogni risultato `relevance_norm`, `recency` e `final_score`.
    """
    if not results or weight <= 0:
        return results
    weight = min(float(weight), 1.0)

    pertinenza = _minmax([float(r.get(score_key, r.get("score", 0.0)) or 0.0) for r in results])

    ordinali = [_ordinale(r.get(date_key)) for r in results]
    datati = [o for o in ordinali if o is not None]
    if datati:
        lo, hi = min(datati), max(datati)
        recenza = [neutral if o is None else (1.0 if hi == lo else (o - lo) / (hi - lo)) for o in ordinali]
    else:
        recenza = [neutral] * len(results)

    for r, p, rec in zip(results, pertinenza, recenza):
        r["relevance_norm"] = round(p, 4)
        r["recency"] = round(rec, 4)
        r["final_score"] = round((1 - weight) * p + weight * rec, 4)

    return sorted(results, key=lambda r: r["final_score"], reverse=True)
