# Ablation sul retrieval — golden dataset v2 (n=30)

Due esecuzioni indipendenti dello stesso studio, stesso giorno (27 agosto 2026, 15:30 e 16:02), stesso dataset (`config/golden_dataset_v2.json`, versione `2.0-draft`, 30 domande). Isola il contributo di reranking, filtro di categoria e top_k senza richiedere generazione (nessuna chiamata all'LLM).

> Le due esecuzioni non producono numeri identici a parita' di configurazione (es. MRR della baseline: 0,215 alle 15:30 contro 0,221 alle 16:02): la ricerca densa su Qdrant/HNSW non e' perfettamente deterministica. Vanno riportate entrambe, non una sola, e la loro differenza e' essa stessa un'indicazione della rumorosita' del sistema a questa numerosita' campionaria.

## Run 15:30 (2026-08-27T15:49:55)

| Configurazione | Hit@3 | Hit@5 | MRR | nDCG@5 | s/domanda |
|---|---|---|---|---|---|
| attuale | 26.7% [14.2%, 44.5%] | 33.3% [19.2%, 51.2%] | 0.265 [0.123, 0.417] | 0.282 [0.139, 0.436] | 16.73 |
| senza reranker | 20.0% [9.5%, 37.3%] | 23.3% [11.8%, 40.9%] | 0.190 [0.067, 0.333] | 0.197 [0.076, 0.337] | 0.17 |
| senza filtro categoria | 33.3% [19.2%, 51.2%] | 40.0% [24.6%, 57.7%] | 0.293 [0.150, 0.444] | 0.323 [0.175, 0.477] | 14.84 |
| top_k = 10 | 20.0% [9.5%, 37.3%] | 30.0% [16.7%, 47.9%] | 0.203 [0.080, 0.343] | 0.227 [0.102, 0.364] | 5.2 |

Confronto appaiato contro la baseline (`attuale`), stadio *context* (dopo reranking, cio’ che riceve davvero il generatore):

| Configurazione | Δ Hit@5 | p (McNemar) | Δ MRR | p (Wilcoxon) | effetto |
|---|---|---|---|---|---|
| senza reranker | -0.100 | 0.3750 | -0.075 | 0.1740 | trascurabile |
| senza filtro categoria | +0.067 | 0.6875 | +0.028 | 0.5580 | trascurabile |
| top_k = 10 | -0.033 | 1.0000 | -0.062 | 0.2623 | trascurabile |

## Run 16:02 (2026-08-27T16:24:31)

| Configurazione | Hit@3 | Hit@5 | MRR | nDCG@5 | s/domanda |
|---|---|---|---|---|---|
| attuale | 33.3% [19.2%, 51.2%] | 36.7% [21.9%, 54.5%] | 0.284 [0.144, 0.434] | 0.303 [0.160, 0.455] | 20.45 |
| senza reranker | 20.0% [9.5%, 37.3%] | 26.7% [14.2%, 44.5%] | 0.198 [0.075, 0.340] | 0.210 [0.088, 0.348] | 0.15 |
| senza filtro categoria | 40.0% [24.6%, 57.7%] | 40.0% [24.6%, 57.7%] | 0.294 [0.161, 0.439] | 0.325 [0.180, 0.477] | 16.58 |
| top_k = 10 | 20.0% [9.5%, 37.3%] | 30.0% [16.7%, 47.9%] | 0.203 [0.080, 0.343] | 0.219 [0.096, 0.354] | 6.33 |

Confronto appaiato contro la baseline (`attuale`), stadio *context* (dopo reranking, cio’ che riceve davvero il generatore):

| Configurazione | Δ Hit@5 | p (McNemar) | Δ MRR | p (Wilcoxon) | effetto |
|---|---|---|---|---|---|
| senza reranker | -0.100 | 0.3750 | -0.086 | 0.1588 | trascurabile |
| senza filtro categoria | +0.033 | 1.0000 | +0.010 | 0.7937 | trascurabile |
| top_k = 10 | -0.067 | 0.6250 | -0.081 | 0.0796 | trascurabile |

## Lettura

Nessuna delle differenze osservate raggiunge la significativita' statistica (p > 0,05 su tutte le metriche, in entrambe le esecuzioni) e la dimensione dell'effetto e' sempre classificata **trascurabile** (delta di Cliff). Il filtro di categoria disattivato mostra un punto stimato piu' alto in entrambe le run (Hit@5: 40,0% contro 33,3%–36,7%), coerente con la decisione presa in `config/rag_config.yaml` (`category_filter: false`) — ma gli intervalli di confidenza al 95% si sovrappongono ampiamente, quindi la decisione va motivata con l'argomento strutturale (le sei categorie non producibili dal classificatore contengono il 75,8% dei chunk dell'indice), non con la significativita' statistica di questo esperimento. E' precisamente il limite dichiarato in §5.1/§7.2 della tesi: n=30 non basta a distinguere configurazioni con questa numerosita' di effetto.

Il reranker mostra il pattern opposto e piu' atteso: rimuoverlo peggiora tutte le metriche in entrambe le run (Hit@5: -10 punti in entrambe), pur restando anch'esso sotto la soglia di significativita' a questa numerosita'.
