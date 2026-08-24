# Valutazione Qualitativa End-to-End e Analisi degli Errori

> Documento complementare a `DOCUMENTAZIONE_PROGETTO.md` e `SPIEGAZIONE_FASI.md`.
> Copre: la metodologia di valutazione qualitativa, il golden dataset, l'harness
> `benchmarks/run_evaluation.py`, la diagnosi del caso "presidente del CNI" e le
> correzioni apportate al sistema.

---

## 1. Perché una nuova valutazione

Il benchmark originale (`benchmarks/run_benchmark.py`) valutava **solo il retrieval**
con *keyword matching*: un chunk era considerato "rilevante" se conteneva una
parola chiave della domanda (es. "presidente"). Conseguenza paradossale osservata:

- La domanda *"Chi è il presidente del CNI?"* riceveva **MRR = 1.0** e **Recall = 1.0**
- Ma il sistema **non riusciva a rispondere** correttamente

Il motivo: il primo chunk recuperato conteneva la parola "presidente" in un
contesto qualsiasi (una news, un PDF di gara), quindi la metrica era soddisfatta,
ma quel chunk non conteneva la risposta. **Le metriche non misuravano la capacità
del sistema di rispondere**, solo la presenza superficiale di termini.

Per una tesi servono risultati dimostrabili end-to-end: metriche di retrieval
calcolate contro **fonti note** e metriche qualitative sulla **risposta generata**.

---

## 2. Il golden dataset (`config/golden_dataset.json`)

Dataset di riferimento con verità nota (*ground truth*), pratica standard nella
letteratura RAG (cfr. RAGAS, BEIR). Ogni item contiene:

| Campo | Significato |
|---|---|
| `question` | Domanda di test |
| `category` | Categoria attesa |
| `reference_answer` | Risposta di riferimento, **estratta dai documenti reali del corpus** |
| `expected_sources` | Frammenti di URL che identificano le fonti corrette |
| `must_contain` | Fatti chiave che la risposta finale deve contenere (es. "Perrini") |

Le risposte di riferimento sono state costruite leggendo i documenti crawlati in
`data/raw/` (es. la pagina `cni/consiglio` riporta "Angelo Domenico Perrini —
Presidente"; la pagina contatti riporta sede e telefono). Sono quindi
**verificabili contro fonte**: nessuna risposta inventata.

> ⚠️ Limitazione dichiarata: 10 item sono sufficienti per una dimostrazione
> metodologica ma statisticamente esigui. Per la tesi è consigliabile arrivare a
> 30-50 domande bilanciate per categoria, con revisione manuale.

---

## 3. L'harness di valutazione (`benchmarks/run_evaluation.py`)

### 3.1 Metriche di retrieval (contro fonti vere)

Un documento è *rilevante* se il suo campo `source` contiene uno dei frammenti
in `expected_sources`.

| Metrica | Definizione |
|---|---|
| `Hit@k` | Frazione di domande con almeno una fonte attesa nei primi k risultati del retrieval |
| `MRR` | Media dei reciprochi dei rank della prima fonte attesa: `1/rank` |
| `Recall` | Frazione di fonti attese effettivamente ritrovate nei candidati |

A differenza del vecchio benchmark, qui la rilevanza è **ancorata alla fonte
corretta**, non a parole chiave superficiali.

### 3.2 Metriche qualitative via LLM-as-judge

Dopo ogni query end-to-end (pipeline completa attraverso l'API), tre giudizi
espressi da qwen2.5:3b in locale su scala 0-5:

| Metrica | Domanda del judge | Cosa intercetta |
|---|---|---|
| `faithfulness` | "La risposta è interamente supportata dai documenti?" | Allucinazioni |
| `answer_relevance` | "Risponde in modo diretto e completo alla domanda?" | Risposte fuori tema o evasive |
| `correctness` | "È coerente con la verità nota (reference answer)?" | Errori fattuali |

Aggiuntivi deterministici:
- `must_contain_pass`: i fatti chiave compaiono nella risposta
- `fallback_triggered`: il sistema ha dichiarato di non sapere
- `first_relevant_rank`, latenza per domanda

### 3.3 Persistenza organizzata per giorno

```
results/
├── 2026-08-24/
│   ├── eval_09-46-50.json        # run completo (config + dettaglio per domanda)
│   ├── eval_FULL1.partial.json   # checkpoint incrementale (resume)
│   └── ...
├── history.csv                   # una riga per (run × domanda): trend nel tempo
├── summary.csv                   # una riga per run: confronto aggregato
└── index.json                    # indice dei run
```

Ogni esecuzione produce una cartella `results/YYYY-MM-DD/`; `summary.csv`
permette di confrontare run successivi (es. prima/dopo una modifica) — utile per
le tabelle sperimentali della tesi.

### 3.4 Uso

```bash
# Run completo con judge
python benchmarks/run_evaluation.py

# Solo retrieval, più veloce
python benchmarks/run_evaluation.py --no-judge

# Prime N domande
python benchmarks/run_evaluation.py --limit 3

# Riprendere un run interrotto (checkpoint dopo ogni domanda)
python benchmarks/run_evaluation.py --run-id FULL1 \
    --resume results/2026-08-24/eval_FULL1.partial.json
```

Requisiti: API attiva su `localhost:8000` (`bash scripts/restart_api.sh --wait`)
e Ollama con `qwen2.5:3b`.

---

## 4. Analisi degli errori: il caso "Chi è il presidente del CNI?"

Caso di studio documentato perché rappresenta il metodo diagnostico usato.

### Situazione iniziale

- Corpus: la pagina `cni.it/cni/consiglio` contiene "Angelo Domenico Perrini — Presidente" ✅
- Metriche vecchie: MRR = 1.0 ✅ (ingannevoli)
- Risposta reale del sistema: *iluzione di non sapere* ❌

### Diagnosi (misurazioni sul campo)

1. **Il chunk giusto esiste ed è indicizzato**: scroll su Qdrant conferma il
   chunk `idx=0` della pagina consiglio ("consiglio / Angelo Domenico Perrini /
   Presidente / Nato ad Alberobello…").
2. **Ma si classifica al rank 20-21** per embedding semantico: il chunk è
   dominato dalla biografia (nascita, laurea, carriera), semanticamente lontano
   da "chi è il presidente". Con `top_k=10` non entrava mai tra i candidati.
3. **Il reranker aggrava il problema**: `cross-encoder/ms-marco-MiniLM-L-6-v2`
   è addestrato su MS MARCO **inglese**: su testo italiano ordina male e scarta
   i chunk utili dal top-5 passato all'LLM.
4. Verifica controllata del nuovo modello: `BAAI/bge-reranker-base` assegna
   score ≈ **0.99** alla coppia (domanda, chunk giusto) vs ≈ 0.00003 a un chunk
   irrilevante → discrimina correttamente in italiano.

### Correzioni applicate (2 righe di config)

```yaml
retrieval:
  top_k: 25            # era 10: ora il chunk giusto entra nei candidati
reranking:
  model: BAAI/bge-reranker-base   # era cross-encoder/ms-marco-MiniLM-L-6-v2
```

Nessuna reindicizzazione necessaria (l'embedding multilingue
`paraphrase-multilingual-MiniLM-L12-v2` non è stato modificato).

### Verifica

Rilanciando la stessa domanda end-to-end il sistema risponde:
*"Angelo Domenico Perrini è il Presidente del Consiglio Nazionale degli
Ingegneri (CNI)"* — `must_contain` superato al 100%.

### Lezioni metodologiche (utili per il capitolo sperimentale)

1. Le metriche vanno validate contro la qualità percepita: MRR alto con risposte
   sbagliate = metrica disallineata dall'obiettivo.
2. In contesti multilingua ogni componente (embedding, reranker, LLM) va scelto
   con copertura linguistica esplicita.
3. Il recall del candidato-set (top_k) vincola tutto ciò che sta a valle: un
   reranker eccellente non può recuperare documenti mai recuperati.
4. L'analisi errore-per-errore (dove esce la risposta giusta? a quale rank?
   chi la scarta?) localizza il colpevole in modo inequivoco.

---

## 5. Limiti noti e lavori futuri

| Aspetto | Stato | Possibile evoluzione |
|---|---|---|
| Dimensione golden dataset | 10 domande | Estendere a 30-50 con revisione manuale |
| Latenza per query | ~5-7 min (LLM 3B su CPU, self-check doppia generazione) | Cache delle query; ridurre rigenerazioni; GPU |
| Duplicati EN/IT | Pagine `/en/...` indicizzate accanto alle IT | Deduplicazione in ingestion o filtro lingua |
| Endpoint API | `async def` con codice sincrono blocca l'event loop durante una query | Spostare la pipeline in threadpool/worker |
| Hybrid search | Config presente ma il retriever usa solo ricerca densa + filtro categoria | Attivare BM25/sparse reale e fusione RRF |
| Judge LLM | Stesso modello del sistema (qwen2.5:3b): possibile bias di autovalutazione | Validare su campione con giudizio umano |

---

## 6. Tracciamento delle modifiche (questa sessione)

| File | Tipo | Modifica |
|---|---|---|
| `config/golden_dataset.json` | nuovo | Golden dataset v1.0 (10 Q/A con fonti attese) |
| `benchmarks/run_evaluation.py` | nuovo | Harness valutazione end-to-end (metriche retrieval + LLM-as-judge + persistenza giornaliera + resume) |
| `scripts/restart_api.sh` | nuovo | Riavvio robusto API (kill forzato, attesa porta/lock, health check) |
| `config/rag_config.yaml` | modifica | `retrieval.top_k` 10→25; `reranking.model` → `BAAI/bge-reranker-base` |
| `src/rag/rag_chain.py` | modifica | `query()` espone anche retrieved/context docs, fallback, grade, self-check |
| `src/api/schemas.py`, `src/api/routes.py` | modifica | `/query` restituisce `fallback_triggered`, `retrieved_docs`, `context_docs` |
| `benchmarks/export_validation_sheet.py` | nuovo | Esporta foglio CSV per validazione umana dei voti del judge |
| `benchmarks/compute_judge_agreement.py` | nuovo | Calcola accordo umano vs judge (MAE, within-1, Pearson) |
| `benchmarks/make_report.py` | nuovo | Genera report aggregato Markdown di un run (`--run <json>`) |
