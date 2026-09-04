# Confronto fra modelli di embedding — golden dataset v2 (n=30)

Eseguito 28/08/2026 (`results/compare_embeddings_2026-08-28_16-39.json`),
con il fix del percorso di embedding applicato (commit `f050a7c`):
`filtro_categoria: false`, coerente con la configurazione di produzione
attuale — a differenza del run precedente (10:19 dello stesso giorno,
inaffidabile per un bug nel percorso di vettorizzazione del modello
"attuale" e un filtro di categoria non allineato alla config).

## Risultato

| Modello | Hit@3 | Hit@5 | MRR | nDCG@5 | Finestra token |
|---|---:|---:|---:|---:|---:|
| attuale (`paraphrase-multilingual-MiniLM-L12-v2`) | 40,0% [24,6%, 57,7%] | 40,0% [24,6%, 57,7%] | 0,294 [0,161, 0,439] | 0,325 [0,180, 0,477] | 128 |
| candidato (`intfloat/multilingual-e5-small`) | 46,7% [30,2%, 63,9%] | 46,7% [30,2%, 63,9%] | 0,378 [0,228, 0,539] | 0,401 [0,247, 0,562] | **512** |

Confronto appaiato contro il modello attuale:

| Metrica | Δ | p | effetto |
|---|---:|---:|---|
| Hit@5 | +0,067 | 0,6875 | trascurabile |
| MRR | +0,083 | 0,1724 | trascurabile |
| nDCG@5 | +0,076 | 0,3316 | trascurabile |

I numeri del modello "attuale" in questo run (Hit@5 40,0%, MRR 0,294)
coincidono esattamente con quelli misurati indipendentemente
nell'ablation e in `FINAL_V2` — conferma diretta che il fix del percorso
di embedding ha funzionato: prima del fix lo stesso modello, sullo
stesso identico compito, risultava a MRR 0,17.

## Lettura

Il candidato fa meglio su **ogni** metrica misurata, ma **nessuna
differenza raggiunge la significatività statistica** a n=30 — stesso
esito già osservato per il filtro di categoria e per il reranker: un
trend positivo e coerente che l'ampiezza del campione non permette di
confermare con certezza statistica.

C'è però un secondo argomento, indipendente dalla statistica: il
candidato ha una finestra di **512 token** contro i **128** del modello
attuale. Dato che i chunk indicizzati hanno una mediana di 266 token
(`results/diagnostics_2026-08-27_12-25.json`), il modello attuale ne
tronca l'82% prima ancora di vettorizzarli (§11.1 di `doc/SISTEMA.md`);
il candidato, con quella finestra, non tronca quasi nulla. Questo è un
fatto verificato, non una stima con incertezza campionaria, e resta
valido indipendentemente dal risultato del test statistico sul
retrieval.

## Raccomandazione

Non adottato in questo lavoro: l'adozione richiederebbe re-indicizzare
l'intera collection di produzione (~73 minuti misurati per 13.784 chunk)
e rilanciare l'intera valutazione end-to-end con generazione (~2,4 ore,
come per `FINAL_V2`), oltre a rifare l'analisi già completata — un
costo non giustificato da un miglioramento non ancora dimostrato con
certezza statistica, a fronte di una scadenza di consegna ravvicinata.
Segnalato come raccomandazione motivata per gli sviluppi futuri (§8):
un candidato con argomento sia statistico (trend positivo, per quanto
non significativo) sia strutturale (elimina il troncamento) a favore
della sua adozione, la cui validazione completa richiede solo tempo,
non ulteriore lavoro di ricerca.
