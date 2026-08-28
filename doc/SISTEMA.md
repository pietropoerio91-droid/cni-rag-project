# Come funziona il sistema — CNI RAG

> Documento unico, verificato contro il codice sorgente attuale (non contro
> versioni precedenti della documentazione). Sostituisce `DOCUMENTAZIONE_PROGETTO.md`,
> `SPIEGAZIONE_FASI.md` e `VALUTAZIONE_QUALITATIVA.md`, che descrivevano stati
> passati del sistema e si erano scollegati dal codice reale su diversi punti
> (modello del reranker, top_k, filtro di categoria, temperatura del LLM,
> elenco degli endpoint). Restano recuperabili nella cronologia git se serve
> confrontare cosa è cambiato e quando.
>
> **Ultima verifica:** 28 agosto 2026, contro il branch `feature/valutazione-statistica`.
> Per la tesi vera e propria: `INDICE_TESI.md` (struttura dei capitoli) e
> `CONCLUSIONI_TESI.md` (capitolo conclusivo, in scrittura).

---

## Indice

1. [Panoramica in una frase](#1-panoramica-in-una-frase)
2. [Stack tecnologico](#2-stack-tecnologico)
3. [Architettura generale](#3-architettura-generale)
4. [Pipeline di ingestion](#4-pipeline-di-ingestion)
5. [Pipeline RAG — LangGraph](#5-pipeline-rag--langgraph)
6. [Governance](#6-governance)
7. [API](#7-api)
8. [Frontend Angular](#8-frontend-angular)
9. [Valutazione e benchmarking](#9-valutazione-e-benchmarking)
10. [Configurazione attuale, con il perché di ogni valore](#10-configurazione-attuale-con-il-perché-di-ogni-valore)
11. [Problemi noti e limiti tecnici confermati](#11-problemi-noti-e-limiti-tecnici-confermati)
12. [Stato del progetto al 28/08/2026 e cosa manca](#12-stato-del-progetto-al-28082026-e-cosa-manca)
13. [Come avviare tutto](#13-come-avviare-tutto)
14. [Mappa verso i capitoli della tesi](#14-mappa-verso-i-capitoli-della-tesi)

---

## 1. Panoramica in una frase

Il sistema risponde in italiano a domande sui dati pubblici del CNI:
scarica il sito `cni.it`, lo trasforma in un indice vettoriale locale, e per
ogni domanda recupera i frammenti di testo più pertinenti, li passa a un LLM
locale (Qwen 2.5 3B via Ollama) che genera la risposta citando le fonti — il
tutto senza inviare mai dati a servizi esterni, su un portatile con 8 GB di
RAM e nessuna GPU.

---

## 2. Stack tecnologico

| Componente | Tecnologia | Ruolo |
|---|---|---|
| Backend | Python + FastAPI | server API |
| Frontend | Angular 18 | interfaccia utente |
| LLM | Qwen 2.5 3B via Ollama (`localhost:11434`) | generazione, grade docs, query rewrite, self-check |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) | vettorizzazione (50+ lingue) |
| Reranker | `BAAI/bge-reranker-base` (cross-encoder multilingue) | riordino dei candidati |
| Vector store | Qdrant, modalità locale su SQLite (`data/qdrant_db`) | database vettoriale |
| Orchestratore | LangGraph | pipeline RAG a 9 nodi + 1 nodo di fallback |
| Framework RAG | LangChain | chunking, wrapper LLM |
| Documenti | httpx + BeautifulSoup + trafilatura + PyMuPDF | crawling e parsing (HTML/PDF) |

Hardware: 8 GB RAM, CPU (nessuna GPU richiesta né usata), nessun Docker
richiesto sulla piattaforma macOS attuale.

---

## 3. Architettura generale

```
INGESTION (una tantum / on-demand via /api/v1/ingest)
  Crawler → Filtro dati pubblici + categorizzazione → Quality check
         → Cleaner → Chunker (1500/200) → Embedder (384-dim) → Indexer (Qdrant)

QUERY (per ogni domanda, orchestrata da LangGraph)
  classify → retrieve → rerank → grade_docs ─┬─pertinente──► build_prompt
                                              └─non pertinente─► rewrite_query
                                                                    │
                                                       retry_count≤1│retry_count>1
                                                          retrieve◄─┘   └──► fallback → END

  build_prompt → generate → self_check ─┬─accurata────► build_citations → END
                                         └─inaccurata + non ancora corretta──► generate (con fix)
```

Sotto ogni fase, con i valori realmente in uso oggi (non quelli storici).

---

## 4. Pipeline di ingestion

### 4.1 Crawler — `src/ingestion/crawler.py` (`CNICrawler`)

Crawler asincrono su `httpx` + `BeautifulSoup`, 5 worker concorrenti su una
coda (`asyncio.Queue`), partendo da `https://www.cni.it`.

- `max_depth: 8`, `max_pages: 15000`, `delay: 0.2s`, `timeout: 15s`, `max_links_per_page: 300`
- `included_paths`: `/media-ing`, `/cni`, `/temi`, `/contatti`, `/servizi` — solo questi vengono seguiti
- `priority_paths` + `priority_max_depth: 12` per dare priorità a `/media-ing` e `/cni`
- `DENIED_PATTERNS`: blocca `/administrator` e **`/en/`** (versione inglese del sito, esclusa — vedi §11)
- PDF: estratti con PyMuPDF, scartati se < 50 caratteri

Output: `list[dict]` con `{url, title, content, meta}`.

### 4.2 Downloader — `src/ingestion/downloader.py`

Salva/carica ogni documento come JSON in `data/raw/`.

### 4.3 Filtro dati pubblici e categorizzazione — `src/governance/public_data_filter.py`

Due funzioni distinte, spesso confuse fra loro nella documentazione precedente:

**`is_public(url, content)`** — blocca path (`/wp-admin`, `/private`, `/restricted`, ecc.) e contenuti con keyword negate (`credenziali`, `non-pubblico`).

**`categorize(url, content)`** — assegna la categoria salvata come metadato di ogni chunk. Prima cerca un pattern URL in `CATEGORY_PATTERNS` (13 categorie: `news`, `documenti`, `normativa`, `formazione`, `commissioni`, `organi`, `servizi`, `eventi`, `temi`, `giornale`, `albo`, `contatti`, `chi_siamo`); se nessun pattern URL matcha, ricade su un punteggio a keyword nel contenuto (`CONTENT_CATEGORY_KEYWORDS`); se ancora nulla, `"generico"`. **14 categorie totali sul corpus.**

> Questa è una categorizzazione diversa e più ricca di quella usata per
> classificare le *domande* dell'utente (§5, nodo `classify`) — è la
> radice del problema di copertura descritto in §11.

### 4.4 Quality check — `src/governance/quality_check.py`

- Lunghezza 50–100.000 caratteri
- Repetition ratio ≤ 0.65 (`1 - parole_uniche/parole_totali`)
- `required_languages: [it]` è **configurato ma non applicato attivamente** (nessun controllo di lingua nel codice)

### 4.5 Cleaner — `src/ingestion/cleaner.py`

Rimuove boilerplate (cookie/privacy banner, "seguici su", ecc.), normalizza whitespace, rimuove righe duplicate consecutive.

### 4.6 Chunker — `src/ingestion/chunker.py`

`RecursiveCharacterTextSplitter` di LangChain: `chunk_size=1500`, `chunk_overlap=200`, separatori `["\n\n", "\n", ".", " ", ""]`.

### 4.7 Embedder — `src/ingestion/embedder.py`

`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensioni, normalizzato, batch 32. **Vedi §11 per il limite di troncamento a 128 token — riguarda proprio questo passaggio.**

### 4.8 Indexer — `src/vectorstore/indexer.py` + `qdrant_client.py`

Qdrant locale su SQLite (`data/qdrant_db`), collezione `cni_documents`, distanza coseno, indice HNSW, dimensione vettori 384. Ogni chunk diventa un `PointStruct` (UUID, vettore, payload con `content/source/title/chunk_index/category`).

**Stato corpus (diagnostica del 27/08):** 17.145 chunk indicizzati, 0% senza categoria, così distribuiti:

| Categoria | Chunk | | Categoria | Chunk |
|---|---:|---|---|---:|
| news | 9.414 | | eventi | 2.876 |
| normativa | 1.813 | | documenti | 870 |
| organi | 536 | | formazione | 505 |
| temi | 258 | | contatti | 175 |
| giornale | 181 | | albo | 166 |
| chi_siamo | 156 | | generico | 106 |
| commissioni | 27 | | servizi | 62 |

---

## 5. Pipeline RAG — LangGraph

### `src/rag/rag_chain.py` (`RAGChain`) — grafo a 10 nodi (9 + fallback), 3 punti con arco condizionale

```python
classify → retrieve → rerank → grade_docs ─┬─► build_prompt → generate → self_check ─┬─► build_citations → END
                                            │                                          │
                                       rewrite_query                              generate (fix, 1 volta sola)
                                            │
                                  retry_count≤1 → retrieve
                                  retry_count>1 → fallback → END
```

| Nodo | Cosa fa |
|---|---|
| `classify` | `QueryClassifier.classify()` — keyword matching sulla domanda, 8 categorie possibili + `"generico"` (vedi §11 per il mismatch con le 14 categorie del corpus) |
| `retrieve` | `HybridRetriever.retrieve()` — vedi sotto |
| `rerank` | `Reranker.rerank()` — cross-encoder `BAAI/bge-reranker-base`, da `top_k=25` candidati a `top_k=5` |
| `grade_docs` | Qwen valuta se i 5 documenti sono pertinenti (`"pertinente"` / `"non pertinente"`) |
| `rewrite_query` | Se non pertinenti, Qwen riscrive la domanda; poi retry (max 1) su `retrieve`, altrimenti `fallback` |
| `build_prompt` | `PromptBuilder` — system prompt + 5 documenti come contesto |
| `generate` | `PIIFilter` sul prompt, poi `ResponseGenerator.generate()` |
| `self_check` | Qwen valuta se la risposta è `"accurata"`; se no, un solo tentativo di rigenerazione con istruzione di correzione |
| `build_citations` | `CitationBuilder` — fonti deduplicate con excerpt e score |
| `fallback` | messaggio "Non ho trovato informazioni sufficienti…" |

**`HybridRetriever.retrieve()` (`src/rag/hybrid_retriever.py`)** — nonostante il nome, oggi fa **solo ricerca densa**: classifica la query, e se `category_filter` fosse attivo (oggi **non lo è**, vedi §10) filtrerebbe per categoria. Non c'è fusione BM25+densa reale: `hybrid_search.enabled: true` in config è un residuo, il codice che leggerebbe `dense_weight`/`sparse_weight` non esiste.

**Metodi pubblici:** `query(question)` (esecuzione sincrona del grafo — usata da `/query`), `astream(question)` (generator manuale, non passa dal grafo LangGraph, per controllo fine sullo streaming SSE).

---

## 6. Governance

| Modulo | File | Funzione |
|---|---|---|
| PII filter | `src/governance/pii_filter.py` | Regex su email, telefono, codice fiscale, P.IVA, SSN. Applicato al prompt prima del LLM e a ogni chunk in streaming |
| Monitoring | `src/governance/monitoring.py` | `RAGMonitor` — traccia ogni query (`trace_id`, eventi per nodo, durata) |
| Filtro dati pubblici | `src/governance/public_data_filter.py` | Vedi §4.3 |
| Quality check | `src/governance/quality_check.py` | Vedi §4.4 |

---

## 7. API

`src/api/main.py`: prefix `/api/v1`, CORS per `http://localhost:4200`. Due router montati: `routes.py` (20 endpoint) e `qdrant_browser.py` (6 endpoint, prefix `/qdrant`) — **26 endpoint in totale**, molti più dei 4 documentati nelle versioni precedenti (query/stream/health/ingest): l'interfaccia di annotazione e la dashboard qualitativa ne hanno aggiunti la maggior parte.

**Query e streaming**
| Metodo | Path |
|---|---|
| POST | `/query` — pipeline completa, sincrona (dal 28/08 non blocca più l'event loop, vedi §11) |
| POST | `/query/stream` | SSE, token per token |
| GET | `/query/log`, `/query/export`, `/query/stats`, `/query/metrics` | log e statistiche delle query servite |
| POST | `/query/feedback` | feedback utente |
| POST | `/query/run-test` | batch di domande di test → accuratezza di classificazione |

**Valutazione e annotazione** (a supporto di §5.5/§6 della tesi)
| Metodo | Path |
|---|---|
| GET | `/evaluation/runs`, `/evaluation/latest`, `/evaluation/questions` | consultazione dei run di `run_evaluation.py` |
| GET | `/evaluation/annotation-queue` | coda di domande da validare manualmente |
| POST | `/evaluation/annotations` | salva un voto umano |
| GET | `/evaluation/agreement` | accordo giudice-umano calcolato al volo |
| GET | `/evaluation/annotations/export.csv` | esporta le annotazioni |

**Sistema**
| Metodo | Path |
|---|---|
| GET | `/health` | Qdrant connesso? LLM raggiungibile? |
| GET | `/benchmark`, `/benchmark/runs/{timestamp}` | risultati di `run_benchmark.py` |
| GET | `/ingest/status` | POST | `/ingest` | avvia/segue crawl + indicizzazione |
| GET | `/qdrant`, `/qdrant/stats`, `/qdrant/documents`, `/qdrant/documents/{id}`, `/qdrant/analytics`, `/qdrant/coverage` | browser e analytics sulla collezione |

---

## 8. Frontend Angular

`frontend/src/app/`:

- **`app.routes.ts`** — due rotte: `/` (chat) e `/statistiche`
- **`components/chat/chat.component.ts`** — chat interattiva: storico, suggerimenti, health check, citazioni cliccabili, streaming
- **`components/statistiche/statistiche.component.ts`** — pagina `/statistiche`, **due tab**: *quantitativa* (grafici su documenti/categorie/lunghezze dall'indice Qdrant) e *qualitativa* (dati dei run di valutazione)
- **`components/statistiche/valutazione.component.ts`** (`<app-valutazione>`) — **non documentato nelle versioni precedenti**: è l'interfaccia di annotazione umana, montata dentro la tab qualitativa. Consuma gli endpoint `/evaluation/*` sopra: mostra la coda di domande da validare in cieco, salva i voti, calcola l'accordo giudice-umano. È lo strumento con cui si esegue la validazione descritta in §5.5 della tesi
- **`services/rag.service.ts`** — client HTTP verso tutti gli endpoint sopra, streaming via XHR (`onprogress`)
- **`models/rag.models.ts`** — interfacce TypeScript corrispondenti

---

## 9. Valutazione e benchmarking

Tre strumenti distinti, non intercambiabili — usare quello giusto per la domanda giusta:

| Script | Cosa misura | Richiede LLM? | Stato dati raccolti |
|---|---|---|---|
| `benchmarks/run_benchmark.py` | retrieval con keyword matching | no | **limite noto**: dà punteggi alti anche quando il sistema non sa rispondere (vedi caso "presidente del CNI" in §11). Da non usare per risultati di tesi |
| `benchmarks/run_evaluation.py` | pipeline end-to-end (retrieval + generazione), contro `config/golden_dataset*.json`, con LLM-as-judge | sì | solo `FULL1` (10 domande, 24/08) committato — troppo esiguo, vedi §12 |
| `benchmarks/ablation_retrieval.py` | solo retrieval/reranking, nessuna generazione — isola l'effetto di `top_k`, reranker, filtro categoria | no | **fatto**: n=30, 27/08, due run — `results/report_ablation_2026-08-27.md` |
| `benchmarks/oracle_context.py` | quota d'errore imputabile al generatore (contesto perfetto per costruzione) | sì | non ancora eseguito |
| `benchmarks/compute_judge_agreement.py` | accordo giudice-umano (kappa, Krippendorff, MAE) | no | dati umani quasi vuoti (solo Q01 in `results/validation_2026-08-26.csv`) |
| `benchmarks/compare_embeddings.py`, `compare_generators.py` | confronto fra modelli alternativi | sì | lavoro in corso, non ancora committato (vedi §12) |
| `benchmarks/stats.py` | libreria condivisa: IC bootstrap/Wilson, Wilcoxon, McNemar, delta di Cliff | — | verificato corretto in questa sessione |
| `benchmarks/metrics.py` | libreria condivisa: definizioni di Hit@k/Recall@k/MRR/nDCG, un'unica definizione di "rilevante" per tutte le metriche | — | verificato corretto in questa sessione |

Golden dataset: `config/golden_dataset.json` (v1, 10 domande) e `config/golden_dataset_v2.json` (v2.0-draft, **30 domande**, usato dall'ablation).

---

## 10. Configurazione attuale, con il perché di ogni valore

Da `config/rag_config.yaml`, con la ragione **reale** dietro ogni scelta (non quella storica):

| Parametro | Valore | Perché |
|---|---|---|
| `embedding.model_name` | `paraphrase-multilingual-MiniLM-L12-v2` | multilingua, sostituisce un modello solo-inglese |
| `llm.temperature` | **0.1** | non 0.2 come riportato nelle versioni precedenti della documentazione — risposte quanto più deterministiche possibile |
| `retrieval.top_k` | 25 | prima era 10: con 10 il chunk corretto per "chi è il presidente del CNI" non entrava mai fra i candidati (si classificava al rango 20-21) |
| `retrieval.category_filter` | **false** | disattivato il 27/08: le 6 categorie non producibili dal classificatore delle query (`chi_siamo`, `eventi`, `generico`, `giornale`, `news`, `temi`) coprono il **75,8%** dei chunk indicizzati — con il filtro attivo, tre domande su quattro perdevano accesso alla maggior parte del corpus |
| `retrieval.hybrid_search.enabled` | true | **valore non funzionale** — nessun codice implementa la fusione dense+sparse, vedi §5 |
| `reranking.model` | `BAAI/bge-reranker-base` | prima era `cross-encoder/ms-marco-MiniLM-L-6-v2` (solo inglese): su testo italiano ordinava male e scartava i chunk utili |
| `reranking.top_k` | 5 | numero di documenti finali passati al LLM |
| `chunking.chunk_size` / `overlap` | 1500 / 200 | pensato per dare contesto sufficiente al LLM — **ma vedi §11, l'embedding ne vede molto meno** |
| `crawler.included_paths` | 5 path | limita il crawl alle sezioni pubbliche rilevanti del sito |
| `crawler` blocca `/en/` | — | 27% dei dati crawlati era in inglese, inutile per utenti italiani |

---

## 11. Problemi noti e limiti tecnici confermati

Verificati in questa sessione contro il codice reale, non riportati per sentito dire.

### 11.1 Troncamento dell'embedding — **non documentato prima d'ora**

Il modello di embedding ha `max_seq_length = 128` token. I chunk indicizzati hanno una mediana di **266 token** (1.170 caratteri). Conseguenza misurata (`results/diagnostics_2026-08-27_12-25.json`):

- **82,2%** dei chunk viene troncato in fase di embedding
- in media si perde il **41,3%** del contenuto di ogni chunk troncato
- il modello "vede" in media solo il **53,6%** del testo di un chunk

Questo è probabilmente un fattore che spiega perché gli Hit@5 misurati
nell'ablation (§9) restano nella fascia 33-40%: `chunk_size=1500` è stato
scelto per dare contesto al *generatore*, ma il *retriever* lavora
sistematicamente su una versione tagliata del chunk. È un disallineamento
diretto fra due parametri della pipeline — non ancora affrontato nel codice
né discusso nella tesi. Possibili correzioni: ridurre `chunk_size` a una
misura compatibile con 128 token (~500-550 caratteri), oppure passare a un
modello di embedding con finestra più ampia.

### 11.2 Endpoint `/query` bloccava l'event loop — **corretto il 28/08**

`chain.query()` è sincrona e può durare 150-750s (embedding, retrieval,
reranking, generazione via Ollama). Chiamata direttamente dentro un
`async def`, bloccava FastAPI per l'intera durata — nessun'altra richiesta,
nemmeno `/health`, veniva servita nel frattempo. Corretto con
`asyncio.to_thread` (commit `dd28f42`). Non ancora validato con `pytest` in
locale.

### 11.3 Ricerca densa non perfettamente deterministica

Due run identici dell'ablation (stesso giorno, 22 minuti di distanza) danno
numeri leggermente diversi a parità di configurazione (es. MRR baseline:
0,215 vs 0,221). Da capire se è varianza di Qdrant/HNSW o dell'indice
stesso — non bloccante, ma va tenuto presente citando i risultati.

### 11.4 Il classificatore delle query copre solo 8 delle 14 categorie del corpus

Vedi §10, riga `category_filter`. Root cause di quella decisione di
configurazione.

### 11.5 Il giudice automatico è lo stesso modello del generatore

`qwen2.5:3b` valuta le risposte che esso stesso (o un modello identico)
genera — rischio noto di bias di self-preference. Mitigato dalla
validazione umana in cieco (§8), che però ha ancora pochissimi dati
raccolti (§12).

### 11.6 Duplicati EN/IT — risolto

Le pagine `/en/` sono ora bloccate dal crawler (§4.1) e uno script dedicato
(`scripts/purge_english_chunks.py`) rimuove i chunk inglesi già indicizzati.

---

## 12. Stato del progetto al 28/08/2026 e cosa manca

**Fatto e verificato in questa sessione:**
- Fix del blocco dell'event loop su `/query` (§11.2) — pushato, da testare in locale con `pytest`
- Recuperato e committato l'ablation study reale del 27/08 (n=30) — `results/report_ablation_2026-08-27.md`
- Verificata la correttezza di `metrics.py` e `stats.py` (le formule che produrranno i numeri della tesi)
- Scoperto e documentato il troncamento dell'embedding (§11.1) — da decidere se correggere prima dei run finali o discutere come limite

**Cosa manca, in ordine di impatto sulla tesi:**

1. **Il run end-to-end finale** su `golden_dataset_v2` (30 domande) con `run_evaluation.py` — è il numero che risponde alla prima metà della domanda di ricerca (accuratezza del sistema). Non fatto.
2. **Il test a contesto oracolo** (`oracle_context.py`) — risponde alla seconda metà della domanda di ricerca (quota d'errore imputabile al generatore/hardware). Non fatto.
3. **Completare la validazione umana**: `results/validation_2026-08-26.csv` ha voti umani solo per 1 domanda su 10. Senza questo, l'accordo giudice-umano (§5.5 della tesi) non ha dati.
4. **Decidere sul troncamento dell'embedding** (§11.1): correggerlo (richiede re-indicizzazione) o riportarlo come limite dichiarato con dati alla mano — è comunque materiale nuovo per §7.2/§7.3 della tesi.
5. **Versionare il lavoro in corso**: risultano non committati `benchmarks/compare_generators.py`, `diagnosi_soglia.py`, `valida_dataset.py`, `config/holdout_v1.json`, `results/compare_embeddings_2026-08-28_10-19.json`, `results/purge_2026-08-27_16-02.json` (visti nello `status` git della sessione) — probabilmente contengono altri risultati utili.
6. **Testare in locale il fix di `/query`** (§11.2) con `pytest`.

**Cosa deve fare tu, concretamente, nell'ordine:**
1. Lanciare `python benchmarks/run_evaluation.py` sul golden dataset v2 completo (richiede API + Ollama attivi)
2. Lanciare `python benchmarks/oracle_context.py --confronta <il file del punto 1>`
3. Completare i voti umani mancanti in `results/validation_2026-08-26.csv`, poi `python benchmarks/compute_judge_agreement.py`
4. Ogni volta che produci un file in `results/`, fai `git add`/`commit`/`push` — è già successo due volte in questa sessione che risultati reali restassero solo sul disco locale
5. Deciso cosa fare del punto 11.1 (troncamento), aggiornarmi e aggiorno `CONCLUSIONI_TESI.md` con i numeri veri

---

## 13. Come avviare tutto

```bash
# Ollama
ollama serve
ollama pull qwen2.5:3b

# Ambiente Python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Ingestion (crawl + indicizzazione) — lunga, esegue tutta la pipeline del §4
python scripts/run_ingestion.py

# API
bash scripts/restart_api.sh --wait   # riavvio robusto, preferibile a run_api.py diretto

# Frontend
cd frontend && npm install && ng serve   # http://localhost:4200
```

Verifica rapida:
```bash
curl http://localhost:8000/api/v1/health
curl -X POST http://localhost:8000/api/v1/query -H "Content-Type: application/json" \
  -d '{"question": "Quali sono gli organi del CNI?"}'
```

---

## 14. Mappa verso i capitoli della tesi

| Sezione di questo documento | Capitolo tesi |
|---|---|
| §2 Stack tecnologico | Cap. 2 |
| §3-§8 Architettura, ingestion, RAG, governance, API, frontend | Cap. 3 (architettura) e Cap. 4 (implementazione) |
| §9 Valutazione e benchmarking | Cap. 5 (metodologia) |
| Risultati prodotti da §9 | Cap. 6 (risultati) |
| §11 Problemi noti | Cap. 7 (discussione, minacce alla validità, limiti) |
| §11.1 (troncamento embedding), hybrid search non reale (§5) | Cap. 8 (sviluppi futuri) |
