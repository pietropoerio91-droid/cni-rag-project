# Documentazione dei test — recupero ibrido

Registro di ogni esperimento eseguito fra il 20 e il 22 settembre 2026, per
arrivare dalla diagnosi (`doc/PIANO_RECUPERO_IBRIDO.md`) alla configurazione
congelata (`doc/SISTEMA.md`, tag `congelato-2026-09-21-e5`). Non è testo da
tesi: è il materiale con cui scriverla — ogni esperimento è riproducibile dal
comando indicato, e ogni numero citato viene da un file specifico in
`results/`, non da un riepilogo a memoria.

**Perché un esperimento in più rispetto al piano iniziale**: la diagnosi
prevedeva 4 passi (denso, denso+BM25, e5 denso, e5+BM25). Ne sono stati fatti
di più perché due scoperte fatte *durante* l'esecuzione hanno cambiato la
domanda: il modello di embedding reale non era quello dichiarato (§3), e la
finestra di 128 token troncava l'81,9% dei chunk (§7) — entrambe hanno aperto
esperimenti che il piano originale non prevedeva.

---

## Riepilogo

| # | Esperimento | Comando | Branch / commit | File dei risultati | Esito |
|---|---|---|---|---|---|
| 1 | Denso vs denso+BM25, modello reale (L6) | `ablation_retrieval.py --preset ibrido` | `exp/retrieval-ibrido` @ `02a36ed` | `ablation_ibrido_passi_0_1.json` | Hit@5 40,0%→66,7% |
| 2 | e5-small, denso vs +BM25 | idem, con `EMBEDDING_MODEL` forzato | `exp/embedding-e5` @ `193a20a` | `ablation_e5_passi_2_3.json` | Hit@5 46,7%→60,0% |
| 3 | Multilingue dichiarato, denso vs +BM25 | idem | `exp/embedding-multilingual` | `ablation_multiling_passi_2_3.json` | Hit@5 50,0%→63,3% |
| 4 | Verifica di riproducibilità (nessuna variabile forzata) | idem, dal repository così com'è | `feature/recupero-ibrido` | `ablation_verifica_integrazione.json` | numeri identici a #3 |
| 5 | Confronto 3 reranker | `ablation_retrieval.py --preset reranker` | `feature/recupero-ibrido` @ `74e932f` | `ablation_reranker.json` | mmarco adottato come deviazione dichiarata (`e46fcc8`) |
| 6 | BM25 nativo vs in memoria (equivalenza) | script dedicato, vedi §8 | `exp/bm25-nativo` @ `17a32a3` | `ablation_bm25_nativo.json` | punteggi identici (Δ 5,5·10⁻⁸) |
| 7 | e5 + BM25 nativo + reranker `mmarco` | idem | `exp/e5-nativo` (primo tentativo) | `ablation_e5_bm25_mmarco.json` | scartato, sotto soglia |
| 8 | e5 + BM25 nativo + `bge-reranker-base` (adottato) | idem | `exp/e5-nativo` @ `9abbe82` | `ablation_e5_bm25_bge_nativo.json` | Hit@5 46,7%→60,0%, adottato |
| 9 | Run end-to-end `FINAL_V3` | `run_evaluation.py --dataset config/golden_dataset_v2.json --run-id FINAL_V3` | `release/recupero-ibrido` @ `c3e6460` | `2026-09-21/eval_14-53-16.json` | accuratezza umana 63,3% |
| 10 | Run definitivo (unione con filtro PII spento) | script Python dedicato, vedi §10 | `release/recupero-ibrido` @ `e91d460` | `2026-09-22/eval_FINAL_V3_DEFINITIVO.json` | numero riportabile in tesi |

Tutti i comandi vanno lanciati con l'API di produzione **ferma** (Qdrant in
locale prende un lock esclusivo di processo) e Ollama attivo.

---

## 1. Denso vs denso+BM25, modello reale (passi 0-1 del piano)

```bash
python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_ibrido_passi_0_1.json
```

Branch `exp/retrieval-ibrido`, commit `02a36ed` (BM25 in memoria e fusione
RRF: `11d6bc0`). Il passo 0 (solo denso) doveva riprodurre `FINAL_V2`: **40,0%
/ 0,294**, identico — è la prova che il codice del retriever non ha
introdotto regressioni prima di misurare l'effetto del BM25.

**Risultato**: denso 40,0% / MRR 0,294 → ibrido **66,7% / 0,437**
(McNemar p=0,008, Wilcoxon su MRR p=0,007).

**Limite**: la diagnosi che ha motivato il BM25 è stata fatta guardando gli
errori di queste stesse 30 domande — va dichiarato come selezione sul set di
valutazione, non come generalizzazione provata (vedi `CONCLUSIONI_TESI.md`).

---

## 2-3. Tre modelli di embedding, denso vs +BM25

```bash
EMBEDDING_MODEL=intfloat/multilingual-e5-small python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_e5_passi_2_3.json
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2 python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_multiling_passi_2_3.json
```

Branch `exp/embedding-e5` (`193a20a`) ed `exp/embedding-multilingual`.
Ciascuno richiede un'indicizzazione preliminare in una collection separata
(`scripts/build_sparse_collection.py` o, per e5, un embedding completo da
zero — ~15 minuti su questo hardware).

**Errore commesso e corretto**: il primo tentativo con e5 è stato lanciato
senza forzare `EMBEDDING_MODEL`, e il `.env` locale sovrascriveva il YAML con
il modello inglese — risultato: 0 candidati su 30 domande. File scartato,
rinominato `ablation_e5_passi_2_3_NON_VALIDO_modello_sbagliato.json` (non
committato). È stato proprio questo errore a far scoprire il problema più
generale del §7.

**Risultato**:

| Embedding | Solo denso | + BM25 |
|---|---:|---:|
| e5-small | 46,7% / 0,378 | 60,0% / 0,434 |
| multilingue (dichiarato) | 50,0% / 0,358 | 63,3% / 0,434 |

**Limite**: BM25 in memoria, non ancora nativo — l'equivalenza è verificata
separatamente (§6).

---

## 4. Verifica di riproducibilità

```bash
python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_verifica_integrazione.json
```

Lanciato dal repository così com'è, **senza nessuna variabile d'ambiente
forzata**, dopo aver integrato tutto in `feature/recupero-ibrido`. Serve a
dimostrare che la configurazione scritta nei file è davvero quella misurata,
non un'esecuzione con parametri impostati a mano che poi non corrispondono al
codice. Risultato identico al #3: 50,0%/0,358 → 63,3%/0,434.

---

## 5. Confronto reranker

```bash
python benchmarks/ablation_retrieval.py --preset reranker --out results/ablation_reranker.json
```

Branch `feature/recupero-ibrido`, preset aggiunto nel commit `74e932f`.
Confronta `bge-reranker-base` (partenza), `mmarco-mMiniLMv2-L12-H384-v1` e
`bge-reranker-v2-m3`, tutti sulla configurazione multilingue+BM25 **prima**
di riconsiderare l'embedding per il troncamento (§7) — quindi non
direttamente sulla configurazione finale (e5).

**Regola di adozione, fissata prima di vedere i dati**: guadagno ≥ 2 domande
su 30 e latenza entro il doppio di quella attuale.

| Reranker | Hit@5 | MRR | s/domanda |
|---|---:|---:|---:|
| bge-reranker-base | 63,3% | 0,434 | 16,4 |
| mmarco-mMiniLMv2-L12-H384-v1 | 66,7% | 0,522 | 9,9 |
| bge-reranker-v2-m3 | 70,0% | 0,541 | 60,2 |

**Esito**: nessuno supera la regola alla lettera (mmarco guadagna 1 domanda;
v2-m3 ne guadagna 2 ma con 3,7× la latenza, quindi escluso). **mmarco fu
comunque adottato** (commit `e46fcc8`, 21/09 mattina) per dominanza su tutte le
metriche, −40% di latenza e addestramento su dati che includono l'italiano,
come **deviazione dalla regola dichiarata nel commit**. È rimasto in
produzione fino al cambio di embedding (§8), dove il confronto è stato
ripetuto e ha dato l'esito opposto.

*Correzione del 24/09*: fino a questa data qui si leggeva «Il reranker resta
`bge-reranker-base`» e «la scelta non è stata ripetuta dopo aver adottato
e5». Entrambe le frasi erano sbagliate: mmarco era stato adottato, e con e5 il
confronto mmarco/bge è stato rifatto (§8). Vedi i commit `e46fcc8` e `9abbe82`.

---

## 6. BM25 nativo in Qdrant vs in memoria — verifica di equivalenza

```bash
python scripts/build_sparse_collection.py --source cni_documents_multiling --target cni_documents_multiling_bm25
python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_bm25_nativo.json
```

Branch `exp/bm25-nativo`, commit `17a32a3` (implementazione:
`src/vectorstore/bm25_sparse.py`). Prima prova di fattibilità su una
collection di test (vettori sparsi con modificatore IDF, fusione RRF lato
server via `Prefetch`+`RrfQuery`), poi confronto diretto sulle 30 domande con
la stessa configurazione di §3 (multilingue+BM25).

**Risultato**: **identico** al BM25 in memoria — differenza relativa massima
dei punteggi 5,5·10⁻⁸, **zero** domande con Hit@5 o posizione diversi.

**Limite tecnico documentato nel codice**: il peso BM25 dipende dalla
lunghezza media dell'intero corpus (`avgdl`); un'aggiunta incrementale di
chunk (senza ricostruire la collection) userebbe un `avgdl` sbagliato — va
sempre ricostruita da zero, mai aggiornata in-place. Dal 23/09 il pulsante di
indicizzazione rispetta questo vincolo per costruzione: costruisce ogni volta una
collection nuova da zero, senza toccare quella in uso (`SISTEMA.md` §11.8, §11.10).

---

## 7. Il troncamento e la riconsiderazione di e5

Non un esperimento con un comando unico, ma un'osservazione empirica: il
modello multilingue dichiarato ha finestra di 128 token, contro una mediana
di 266 token per chunk. Misurato sul corpus reale:

```bash
python -c "
from transformers import AutoTokenizer
# ... conteggio token per chunk, vedi cronologia dei comandi eseguiti in sessione
"
```

**Risultato**: 81,9% dei chunk troncati con il modello multilingue, contro
**0,13%** (18 chunk su 13.784) con e5-small (finestra 512 token). Questo ha
riaperto la domanda su e5, già scartato al passo 2-3, portando ai test #7-8.

---

## 8. e5 + BM25 nativo: due reranker a confronto

```bash
python scripts/build_sparse_collection.py --source cni_documents_e5 --target cni_documents_e5_bm25
EMBEDDING_MODEL=intfloat/multilingual-e5-small python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_e5_bm25_mmarco.json   # reranker mmarco: scartato
# poi, cambiato reranking.model a BAAI/bge-reranker-base in config/rag_config.yaml:
python benchmarks/ablation_retrieval.py --preset ibrido --out results/ablation_e5_bm25_bge_nativo.json   # adottato
```

Branch `exp/e5-nativo`. Due tentativi, non uno:

| Reranker | Fonte nei 25 candidati | Hit@5 dopo reranker |
|---|---:|---:|
| `mmarco` (quello scelto al §5) | 24/30 | 16/30 (MRR 0,412, 8,7 s/domanda) — **sotto la soglia di adozione**, scartato |
| `bge-reranker-base` (quello di partenza) | 24/30 | 18/30 (MRR 0,434, 17,6 s/domanda) — **adottato** |

File dei risultati: `results/ablation_e5_bm25_mmarco.json` (portato su `main`
il 24/09; prima era solo sul branch `exp/e5-nativo`) e
`results/ablation_e5_bm25_bge_nativo.json`.

**Con e5 l'ordine dei due reranker si inverte.** Con mmarco il BM25 non
aggiunge nulla (16/30 con e senza BM25), con bge-reranker-base porta da 14/30 a
18/30: su questi candidati mmarco scarta proprio i documenti che il canale
lessicale recupera. Per questo in produzione resta bge-reranker-base.

**Perché la configurazione finale è stata preferita a `multilingue+mmarco`**,
che aveva un punteggio nominalmente più alto (20/30 = 66,7% contro 18/30 =
60,0%): decisione di progetto, eliminare il troncamento dell'81,9% dei chunk
(§7), non una soglia numerica. La differenza di 2 domande su 30 non è
distinguibile dal rumore. Va dichiarato che, rispetto a quella configurazione,
cambiano due componenti (embedding e reranker), non uno. Verificato con BM25
nativo: **60,0% / 0,434**, identico alla misura con BM25 in memoria del passo 2
(§3).

**Limite**: `bge-reranker-v2-m3` non è stato ripetuto con e5. Era già escluso
per la latenza (3,7 volte quella di partenza), che dipende dal reranker e non
dall'embedding. Resta invece il limite generale: anche questa scelta è fatta
sulle stesse 30 domande su cui poi è misurato il sistema.

---

## 9. Run end-to-end `FINAL_V3`

```bash
python scripts/run_api.py --no-reload &
python benchmarks/run_evaluation.py --dataset config/golden_dataset_v2.json --run-id FINAL_V3
```

Configurazione congelata (tag `congelato-2026-09-21-e5`, commit `55eb2f1`):
e5-small + BM25 nativo (RRF k=60) + `bge-reranker-base` + `qwen2.5:3b`. Stesso
dataset, stesso giudice automatico, stessa procedura di `FINAL_V2` — l'unica
variabile cambiata è il sistema.

**Modifica post-congelamento**: il filtro PII (`governance.pii_filter`, vedi
`SISTEMA.md` §11.9) era ancora attivo durante questo run e ha reso
impossibili Q06 e Q12. Disattivato subito dopo (commit `94bdb96`); le due
domande sono state rilanciate a parte (run `FINAL_V3_PII` e
`FINAL_V3_PII_Q12`, un dataset a una sola domanda ciascuno) e integrate nel
run definitivo (§10).

**Risultato**: 30/30 domande completate, contesto Hit@5 60,0% / MRR 0,434
(coincide col passo 8 — stesso sistema, dataset di valutazione più ampio
rispetto all'ablation solo perché include anche la generazione).

**Limite**: da solo non è il numero da citare in tesi — Q06 e Q12 vanno
sostituite col run a filtro spento (§10), altrimenti l'accuratezza risulta
artificialmente più bassa per un motivo di configurazione, non di sistema.

---

## 10. Run definitivo

Non un nuovo run del sistema, ma la **ricomposizione** del run #9 sostituendo
Q06 e Q12 con le loro esecuzioni a filtro PII spento, seguita dal ricalcolo di
tutte le metriche (recupero, accordo giudice-umano, confronto con `FINAL_V2`)
sulle 30 domande risultanti. Verificato che l'endpoint `/evaluation/agreement`
del backend, interrogato dal vivo su questo run, produce **esattamente** gli
stessi numeri del calcolo offline (kappa medio 0,540) — due implementazioni
indipendenti della stessa formula danno lo stesso risultato.

**File**: `results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json` (contiene anche
`provenienza`, con l'elenco esatto dei tre run sorgente e dei commit di
riferimento), `results/2026-09-22/RIEPILOGO_FINAL_V3.md` (tabelle pronte per
la tesi), `results/judge_agreement_2026-09-22.json`,
`results/annotations_FINAL_V3_DEFINITIVO.json` (le 30 annotazioni umane
unite, corrette dopo revisione su 4 domande — vedi la cronologia dei commit
`ea1eeb2` e `e91d460`).

**Limite dichiarato nel file stesso**: è un run "composito", non una singola
esecuzione continua — va descritto come tale in tesi (§3.7, protocollo
sperimentale), non presentato come se fosse un run unico dall'inizio alla
fine.

**Limite di riproducibilità**: lo script che ha fatto l'unione e il ricalcolo
era una sessione Python ad-hoc, non salvata nel repository — non c'è un
comando unico da rilanciare per rigenerare questi file da zero. I dati non
sono a rischio (sono committati, e il calcolo dell'accordo è stato
verificato due volte in modo indipendente: offline e dal vivo tramite
l'endpoint `/evaluation/agreement`, con lo stesso risultato), ma manca lo
script stesso. Da scrivere se serve rigenerare l'unione — la logica è: unire
i tre `results` per `question_id`, unire le tre `annotations_*.json`, poi
`benchmarks.metrics`/`benchmarks.stats` per le metriche di recupero e
`benchmarks.agreement.report_completo` per l'accordo, esattamente come fa
`src/api/routes.py::evaluation_agreement`.

---

## Esperimenti collaterali, non nella sequenza principale

- **Whitelist del crawler** (`config/whitelist-crawler` @ `3780a0a`): non un
  test di retrieval, ma un'analisi statica del sito (confronto fra i link
  della home e i percorsi già indicizzati) — nessuna ingestion eseguita.
- **`/area-cni` e Q22**: deliberatamente non testato. Richiederebbe
  un'ingestion mirata su una collection separata; rimandato a dopo la
  chiusura della tesi (vedi `SISTEMA.md` §12).

---

## Dove trovare cosa

| Voglio... | Guardo |
|---|---|
| I numeri finali, pronti per la tesi | `results/2026-09-22/RIEPILOGO_FINAL_V3.md` |
| Il perché delle scelte di progetto | `doc/PIANO_RECUPERO_IBRIDO.md` (diagnosi iniziale) e questo file (esiti ed evoluzione) |
| Lo stato attuale del sistema, file per file | `doc/SISTEMA.md` |
| Come è organizzato il lavoro fra branch | `doc/SISTEMA.md` §12, elenco commit sopra |
| Un singolo file di risultati | `results/ablation_*.json` (elenco §1-10) o `results/2026-09-2*/eval_*.json` |
