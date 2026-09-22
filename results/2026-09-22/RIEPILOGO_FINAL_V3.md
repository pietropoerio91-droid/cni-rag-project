# FINAL_V3 — run definitivo, risultati e confronto con FINAL_V2

Generato il 2026-09-22T07:40:01. Vedi `provenienza` nel file JSON per la costruzione del run.

**Configurazione**: embedding `intfloat/multilingual-e5-small`, recupero ibrido (denso + BM25 nativo in Qdrant, RRF k=60), reranker `BAAI/bge-reranker-base`, generatore `qwen2.5:3b`. Filtro PII disattivato (governance.pii_filter.enabled: false). Tag di congelamento: `congelato-2026-09-21-e5` (commit 55eb2f1); filtro PII disattivato nel commit successivo 94bdb96.

## 1. Metriche di recupero (contesto passato al generatore, n=30, IC 95%)

| Metrica | FINAL_V2 | FINAL_V3 | Δ | p | effetto |
|---|---:|---:|---:|---:|---|
| Hit@3 | 40.0% | 50.0% | +0.100 | 0.3750 | trascurabile |
| Hit@5 | 40.0% | 60.0% | +0.200 | 0.0703 | piccola |
| MRR | 0.294 | 0.434 | +0.140 | 0.0278 | piccola |
| Recall@5 | 0.400 | 0.600 | +0.200 | 0.0339 | piccola |
| nDCG@5 | 0.325 | 0.478 | +0.153 | 0.0253 | piccola |

## 2. Accuratezza umana (correttezza ≥ 4)

- **FINAL_V2**: 13/30 = 43,3%
- **FINAL_V3**: 19/30 = 63.3% [45.5%, 78.1%]
- Δ accuratezza binaria = +0.200, p = 0.1460 (mcnemar_exact)
- Δ correttezza media (continua, 0-5) = +1.300, p = 0.0085 (Wilcoxon)
- media fedeltà: 4.733 · media pertinenza: 3.9 · media correttezza: 3.567

## 3. Decomposizione dell'errore per stadio (annotazione umana)

| Stadio | FINAL_V2 | FINAL_V3 |
|---|---:|---:|
| `ok` | 13 (43%) | 19 (63%) |
| `retrieval_miss` | 14 (47%) | 2 (7%) |
| `reranker_drop` | 1 (3%) | 1 (3%) |
| `generation_miss` | 2 (7%) | 8 (27%) |

Nota: il rapporto errore-a-monte (retrieval_miss + reranker_drop) contro errore-di-generazione (generation_miss + hallucination) passa da 15:2 a 3:8 — il recupero migliora, il collo di bottiglia si sposta sul generatore.

## 4. Accordo giudice-umano (NON validato)

| Metrica | n | kappa quadratico | alfa di Krippendorff | MAE | accordo esatto | entro 1 |
|---|---:|---:|---:|---:|---:|---:|
| Fedeltà | 30 | 0.283 | 0.181 | 1.2 | 33% | 70% |
| Pertinenza | 30 | 0.865 | 0.867 | 0.5 | 63% | 90% |
| Correttezza | 30 | 0.471 | 0.402 | 1.667 | 30% | 63% |

**Kappa medio: 0.54** — Accordo sotto la soglia di utilizzabilità dichiarata (0.61): i punteggi automatici non sono riportati come misura affidabile in questo lavoro. L'assenza di accordo è documentata come risultato della validazione, non omessa.

Il giudice usa lo stesso modello del generatore (`qwen2.5:3b`): sì, rischio di bias di self-preference.

## 5. Note metodologiche da dichiarare in tesi

- Il run è costruito unendo tre esecuzioni: le 28 domande di `FINAL_V3` (filtro PII attivo, ininfluente per esse) più Q06 e Q12 rilanciate con il filtro PII disattivato, l'unica configurazione correttamente valutabile per quelle due domande.
- FINAL_V2 è stato prodotto con `all-MiniLM-L6-v2` (embedding inglese), diverso da quello dichiarato nel config_snapshot dell'epoca (`paraphrase-multilingual-MiniLM-L12-v2`).
- I punteggi del giudice automatico non sono validati (kappa medio sotto la soglia 0,61): l'accuratezza da riportare come risultato principale è quella umana.
- Q12: correttamente `generation_miss` (informazione nel contesto, non estratta), non `retrieval_miss` — verificato leggendo il contenuto integrale dei documenti passati al modello.
- Q02: `reranker_drop` (fonte recuperata al rango 22, scartata dal reranker), non `retrieval_miss`.
- Q22: falso negativo della metrica automatica sulla pagina attesa (match di sottostringa su un URL non pertinente); la fonte corretta non è mai fra i candidati — confermato `retrieval_miss`.
- Q24: falso negativo della metrica sulla pagina attesa; una pagina topicamente pertinente (6ª edizione dell'evento, 2018) era fra i candidati passati al modello, che ha risposto con un'imprecisione (correttezza 3) — `generation_miss`.
- n=30: nessun risultato qui è significativo nel senso della potenza statistica classica; i p-value sono riportati come indicazione descrittiva, non come prova.
