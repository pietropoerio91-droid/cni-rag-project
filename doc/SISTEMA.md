# Come funziona il sistema — CNI RAG

> Documento unico, verificato contro il codice sorgente attuale (non contro
> versioni precedenti della documentazione). Sostituisce `DOCUMENTAZIONE_PROGETTO.md`,
> `SPIEGAZIONE_FASI.md` e `VALUTAZIONE_QUALITATIVA.md`, che descrivevano stati
> passati del sistema e si erano scollegati dal codice reale su diversi punti
> (modello del reranker, top_k, filtro di categoria, temperatura del LLM,
> elenco degli endpoint). Restano recuperabili nella cronologia git se serve
> confrontare cosa è cambiato e quando.
>
> **Ultima verifica:** 22 settembre 2026, contro il branch `release/recupero-ibrido`
> (configurazione congelata, tag `congelato-2026-09-21-e5`). Aggiorna la versione
> del 3 settembre dopo il lavoro sul recupero ibrido: le sezioni toccate sono
> segnalate esplicitamente. Per la tesi vera e propria: `INDICE_TESI.md`
> (struttura a 6 capitoli, su `origin/main`) e `CONCLUSIONI_TESI.md`.

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
12. [Stato del progetto al 23/09/2026 e cosa manca](#12-stato-del-progetto-al-23092026-e-cosa-manca)
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
| Embeddings | `intfloat/multilingual-e5-small` (384-dim, finestra 512 token) | vettorizzazione, prefissi `query:`/`passage:` automatici — **cambiato dal 21/09**, vedi §11.1 |
| Reranker | `BAAI/bge-reranker-base` (cross-encoder multilingue) | riordino dei candidati |
| Vector store | Qdrant, modalità locale su SQLite (`data/qdrant_db`), collection `cni_documents_e5_bm25` | database vettoriale — **ibrido dal 21/09**: ogni chunk ha un vettore denso e uno sparso BM25, fusi con Reciprocal Rank Fusion (vedi §5) |
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
>
> **Percorsi nuovi della whitelist (corretto il 23/09)**: i percorsi aggiunti
> al crawler il 21/09 (`/area-cni`, `/faq`, `/sezioni-amministrazione-trasparente`
> e altri, §10) hanno una categoria in `WHITELIST_PATH_CATEGORIES`, confrontata
> come prefisso del path e **dopo** `CATEGORY_PATTERNS`: gli URL che già
> ricevevano una categoria dai pattern la conservano identica. Vedi §11.7.

### 4.4 Quality check — `src/governance/quality_check.py`

- Lunghezza 50–100.000 caratteri
- Repetition ratio ≤ 0.65 (`1 - parole_uniche/parole_totali`)
- `required_languages: [it]` è **configurato ma non applicato attivamente** (nessun controllo di lingua nel codice)

### 4.5 Cleaner — `src/ingestion/cleaner.py`

Rimuove boilerplate (cookie/privacy banner, "seguici su", ecc.), normalizza whitespace, rimuove righe duplicate consecutive.

### 4.6 Chunker — `src/ingestion/chunker.py`

`RecursiveCharacterTextSplitter` di LangChain: `chunk_size=1500`, `chunk_overlap=200`, separatori `["\n\n", "\n", ".", " ", ""]`.

### 4.7 Embedder — `src/ingestion/embedder.py`

`intfloat/multilingual-e5-small`, 384 dimensioni, finestra 512 token, normalizzato, batch 32. **Cambiato dal `paraphrase-multilingual-MiniLM-L12-v2` (finestra 128 token) il 21/09** proprio per risolvere il troncamento descritto in §11.1 — l'ex-limite più grave del sistema.

`ModelFactory.resolve_embedding_model()` (`src/core/model_factory.py`) risolve il modello effettivo e segnala se una variabile d'ambiente (`EMBEDDING_MODEL`) sovrascrive il YAML — vedi §11.5 per perché questo controllo esiste.

I prefissi `query: `/`passage: ` richiesti da e5 sono applicati in modo trasparente da `PrefixedEmbeddings`, dedotti dal nome del modello (`PREFISSI_PER_FAMIGLIA`): nessun punto di chiamata deve saperne nulla.

### 4.8 Indexer — `src/vectorstore/indexer.py` + `qdrant_client.py`

Qdrant locale su SQLite (`data/qdrant_db`), collection `cni_documents_e5_bm25`, dimensione vettori 384. **Dal 21/09 ogni chunk ha due vettori**, non uno: `dense` (denso, distanza coseno, HNSW) e `bm25` (sparso, con modificatore `IDF` calcolato da Qdrant sull'intera collection) — lo schema è definito una sola volta in `src/vectorstore/bm25_sparse.py::collection_schema()` e riusato sia dal gestore Qdrant sia dallo script di costruzione, per evitare che punti diversi del codice creino formati diversi (è successo, vedi §11.6).

Il peso BM25 di ogni chunk dipende dalla lunghezza media dell'intero corpus (`avgdl`): va calcolato in un'unica passata su tutti i chunk, non aggiunto in modo incrementale. Dal 23/09 `index_chunks()` calcola `avgdl` sull'intero corpus e poi invia i punti a Qdrant a lotti di 256 (§11.8); `VectorIndexer(collection_name=...)` scrive su una collection diversa da quella di produzione, usata dal pulsante "Indicizza Dati" (§11.10).

**Stato corpus (22/09, collection `cni_documents_e5_bm25`):** 13.784 chunk, 14 categorie:

| Categoria | Chunk | | Categoria | Chunk |
|---|---:|---|---|---:|
| news | 6.688 | | eventi | 2.711 |
| normativa | 1.749 | | documenti | 828 |
| organi | 480 | | formazione | 391 |
| temi | 221 | | giornale | 157 |
| albo | 156 | | contatti | 153 |
| chi_siamo | 128 | | generico | 57 |
| servizi | 51 | | commissioni | 14 |

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

**`HybridRetriever.retrieve()` (`src/rag/hybrid_retriever.py`)** — **dal 21/09 il nome è finalmente vero**: con `hybrid_search.enabled: true` (valore attuale) esegue una sola chiamata a Qdrant con due `Prefetch` (denso e sparso BM25) fusi lato server con Reciprocal Rank Fusion (`RrfQuery`, `rrf_k=60`) — non una somma pesata: i punteggi coseno e BM25 vivono su scale incomparabili, sui ranghi non serve normalizzare né tarare pesi. Classifica comunque la query per l'eventuale filtro di categoria (oggi **non attivo**, vedi §10), che riguarda solo il canale denso. Con `hybrid_search.enabled: false` il comportamento torna quello di prima (solo denso), utile per misurare il contributo del canale lessicale — è così che sono stati prodotti i confronti in §9.

**Metodi pubblici:** `query(question)` (esecuzione sincrona del grafo — usata da `/query`), `astream(question)` (generator manuale, non passa dal grafo LangGraph, per controllo fine sullo streaming SSE).

---

## 6. Governance

| Modulo | File | Funzione |
|---|---|---|
| PII filter | `src/governance/pii_filter.py` | Regex su email, telefono, codice fiscale, P.IVA, SSN. Applicato a **tutto** il prompt prima del LLM (contesto incluso) e a ogni chunk in streaming. **Configurabile dal 21/09** (`governance.pii_filter.enabled`, oggi **false**): il corpus è interamente pubblico, mascherare i contatti istituzionali del CNI non protegge nessun dato riservato e rendeva impossibili due domande del golden dataset (vedi §11.9) |
| Monitoring | `src/governance/monitoring.py` | `RAGMonitor` — traccia ogni query (`trace_id`, eventi per nodo, durata) |
| Filtro dati pubblici | `src/governance/public_data_filter.py` | Vedi §4.3 |
| Quality check | `src/governance/quality_check.py` | Vedi §4.4 |

---

## 7. API

`src/api/main.py`: prefix `/api/v1`, CORS per `http://localhost:4200`. Due router montati: `routes.py` (23 endpoint) e `qdrant_browser.py` (6 endpoint, prefix `/qdrant`) — **29 endpoint in totale** (i 3 più recenti, dal 23/09, sono `/collections`, `/collections/active` e il campo `collection` in `/ingest/status`; vedi sotto), molti più dei 4 documentati nelle versioni precedenti (query/stream/health/ingest): l'interfaccia di annotazione e la dashboard qualitativa ne hanno aggiunti la maggior parte.

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
| GET | `/evaluation/runs`, `/evaluation/latest`, `/evaluation/questions` | consultazione dei run di `run_evaluation.py`. `/evaluation/latest` espone anche `embedding_effettivo`, e per un run costruito unendo più esecuzioni (vedi `provenienza` nel JSON) anche `confronto_vs_final_v2` e `valutazione_umana` — **dal 22/09** |
| GET | `/evaluation/annotation-queue` | coda di domande da validare manualmente |
| POST | `/evaluation/annotations` | salva un voto umano |
| GET | `/evaluation/agreement` | accordo giudice-umano calcolato al volo |
| GET | `/evaluation/annotations/export.csv` | esporta le annotazioni |
| GET | `/evaluation/ablation-matrix` | **nuovo dal 22/09** — riepilogo degli esperimenti di ablation (matrice embedding × BM25, confronto reranker, verifica BM25 nativo vs in memoria), da file fissi e noti in `results/` |

**Sistema**
| Metodo | Path |
|---|---|
| GET | `/health` | Qdrant connesso? LLM raggiungibile? |
| GET | `/benchmark`, `/benchmark/runs/{timestamp}` | risultati di `run_benchmark.py` |
| GET | `/ingest/status` | POST | `/ingest` | avvia/segue crawl + indicizzazione, **dal 23/09 su una collection nuova** (§11.10) |
| GET | `/collections` | **nuovo dal 23/09** — collection presenti in Qdrant: chunk, compatibilità col retriever, quale è attiva |
| PUT | `/collections/active` | **nuovo dal 23/09** — cambia la collection attiva (rifiutato durante un'indicizzazione o per collection incompatibili) |
| GET | `/qdrant`, `/qdrant/stats`, `/qdrant/documents`, `/qdrant/documents/{id}`, `/qdrant/analytics`, `/qdrant/coverage` | browser e analytics sulla collezione |

---

## 8. Frontend Angular

`frontend/src/app/`:

- **`app.routes.ts`** — due rotte: `/` (chat) e `/statistiche`
- **`components/chat/chat.component.ts`** — chat interattiva: storico, suggerimenti, health check, citazioni cliccabili, streaming. **Dal 24/09** le 6 domande suggerite sono domande del golden dataset con voto massimo (5/5 su correttezza, pertinenza e fedeltà) nell'annotazione umana di `FINAL_V3` e must-contain superato, una per argomento, con il testo identico a quello valutato (Q05, Q10, Q04, Q16, Q11, Q19)
- **`components/statistiche/statistiche.component.ts`** — pagina `/statistiche`, riorganizzata il 24/09 perché ogni dato compaia una volta sola. Due tab, ciascuno con le sue viste e una riga di descrizione per vista; **un solo selettore del run** vale per tutte le viste che dipendono dal run:

  | Tab | Vista | Contenuto |
  |---|---|---|
  | Quantitative | Corpus | composizione della collection attiva (chunk, categorie, lunghezze, fonti, copertura); avviso se la collection è vuota |
  | | Risultati | accuratezza umana, must-contain, fallback, latenza; configurazione del run; recupero prima e dopo il reranking |
  | | Confronto con FINAL_V2 | totali appaiati (recupero e valutazione umana) e tassonomia degli errori V2 contro il run |
  | | Ablation | matrice embedding × BM25, confronto reranker, verifica BM25 nativo contro in memoria |
  | Qualitative | Per domanda | distribuzione degli stadi di errore e dettaglio per domanda (rank, must-contain, stadio, latenza) |
  | | Confronto per domanda | ogni domanda contro FINAL_V2: migliorata, peggiorata o invariata (correttezza ≥ 4), con lo stadio nei due run |
  | | Giudice vs umano | validazione del giudice: κ, bias, MAE, α, matrici di confusione; unico posto dove compaiono i punteggi del giudice |
  | | Annotazione | annotazione umana in cieco |
  | | Telemetria dal vivo | grandezze descrittive sulle query reali della chat |
- **`components/statistiche/valutazione.component.ts`** (`<app-valutazione>`) — le viste che dipendono dal run (Risultati, Confronto con FINAL_V2, Per domanda, Confronto per domanda, Giudice vs umano, Annotazione). Riceve dal padre la vista e il run selezionato; consuma gli endpoint `/evaluation/*`. È lo strumento con cui si esegue la validazione descritta in §5.5 della tesi
- **`app.component.ts`** — intestazione e menu impostazioni: stato della connessione, pulsante "Indicizza Dati" e, **dal 23/09**, la sezione *Collection* per vedere le collection presenti e scegliere quale usare (§11.10)
- **`services/rag.service.ts`** — client HTTP verso tutti gli endpoint sopra, streaming via XHR (`onprogress`)
- **`models/rag.models.ts`** — interfacce TypeScript corrispondenti

---

## 9. Valutazione e benchmarking

Tre strumenti distinti, non intercambiabili — usare quello giusto per la domanda giusta:

| Script | Cosa misura | Richiede LLM? | Stato dati raccolti |
|---|---|---|---|
| `benchmarks/run_benchmark.py` | retrieval con keyword matching | no | **limite noto**: dà punteggi alti anche quando il sistema non sa rispondere (vedi caso "presidente del CNI" in §11). Da non usare per risultati di tesi |
| `benchmarks/run_evaluation.py` | pipeline end-to-end (retrieval + generazione), contro `config/golden_dataset*.json`, con LLM-as-judge | sì | **fatto due volte**: `FINAL_V2` (n=30, 28/08, modello di embedding reale `all-MiniLM-L6-v2` — mai dichiarato, vedi §11.5) e `FINAL_V3` (n=30, 21/09, configurazione congelata e5+BM25 nativo+bge-reranker-base). Il run "definitivo" per la tesi è `results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json`, costruito unendo `FINAL_V3` con due domande rilanciate a filtro PII spento (vedi §11.9) — riepilogo leggibile in `results/2026-09-22/RIEPILOGO_FINAL_V3.md` |
| `benchmarks/ablation_retrieval.py` | solo retrieval/reranking, nessuna generazione — isola l'effetto di `top_k`, reranker, filtro categoria, embedding, BM25 | no | **fatto molte volte**: preset `ibrido` (denso vs denso+BM25, per 3 modelli di embedding) e `reranker` (3 cross-encoder a confronto), tutti in `results/ablation_*.json`, riassunti dall'endpoint `/evaluation/ablation-matrix` (§7) |
| `benchmarks/oracle_context.py` | quota d'errore imputabile al generatore (contesto perfetto per costruzione) | sì | **fatto**: n=30, 28/08 — `results/report_oracle_context.md` |
| `benchmarks/compute_judge_agreement.py` | accordo giudice-umano da un CSV compilato a mano | no | **script obsoleto**, formato CSV superato dal flusso reale (annotazione via frontend → JSON). Il calcolo effettivo passa dall'endpoint `/evaluation/agreement` (`src/api/routes.py`), che usa `benchmarks/agreement.py::report_completo` sul JSON di `results/annotations_*.json` |
| `benchmarks/agreement.py` | libreria: kappa pesato, α di Krippendorff, MAE, matrice di confusione — usata da `/evaluation/agreement` | no | **fatto**: eseguito su `FINAL_V2`, 03/09 — `results/report_judge_agreement.md` |
| `benchmarks/compare_embeddings.py` | confronto fra modello di embedding attuale e candidato (`e5-small`) | sì | **fatto**: 28/08 — `results/report_compare_embeddings.md` |
| `benchmarks/compare_generators.py` | confronto fra generatori locali (qwen2.5:3b vs llama3.2:3b/phi3.5), contesto congelato | sì | script pronto, **mai eseguito** — nessun `results/generators_*.json`. Richiede scaricare modelli extra (~2GB l'uno) e ore di run su CPU per la fase qualità; la fase prestazioni da sola è questione di minuti (`--solo-prestazioni`). Trattato come lavoro futuro, non necessario per rispondere alla domanda di ricerca |
| `benchmarks/valida_dataset.py` | valida un dataset di valutazione prima di lanciare un run (campi obbligatori, id duplicati, criteri irraggiungibili, sovrapposizione lessicale con un altro dataset) | no | strumento di controllo qualità, non produce risultati di tesi di per sé |
| `benchmarks/stats.py` | libreria condivisa: IC bootstrap/Wilson, Wilcoxon, McNemar, delta di Cliff | — | verificato corretto in questa sessione |
| `benchmarks/metrics.py` | libreria condivisa: definizioni di Hit@k/Recall@k/MRR/nDCG, un'unica definizione di "rilevante" per tutte le metriche | — | verificato corretto in questa sessione |

Golden dataset: `config/golden_dataset.json` (v1, 10 domande) e `config/golden_dataset_v2.json` (v2.0-draft, **30 domande**, usato da tutti e quattro gli esperimenti completati).

`config/holdout_v1.json` è un **scaffold vuoto** (10 id, tutti i campi da compilare): l'idea è un insieme di controllo scritto senza guardare l'indice, per stimare se la configurazione scelta con l'ablation generalizza fuori dal golden dataset v2. Non è mai stato compilato né eseguito — trattato come lavoro futuro (vedi §12 e i limiti in `CONCLUSIONI_TESI.md`).

**Aggiornamento 22/09 — esito del recupero ibrido.** Sulle stesse 30 domande, `all-MiniLM-L6-v2 + BM25` porta Hit@5 dal 40,0% al 66,7%; la configurazione adottata (`e5-small + BM25 nativo + bge-reranker-base`) porta il **contesto passato al generatore** dal 40,0% al 60,0% (MRR 0,294→0,434) e **l'accuratezza umana** dal 43,3% al 63,3% (13→19 su 30, Wilcoxon su correttezza continua p=0,0085). La decomposizione per stadio si sposta: `retrieval_miss` 14→2, `generation_miss` 2→8 — il collo di bottiglia passa dal recupero al generatore. L'accordo giudice-umano resta sotto soglia (kappa medio 0,540, come in `FINAL_V2`): l'accuratezza da citare è quella umana. Scripts e file usati per ogni esperimento: vedi `doc/PIANO_RECUPERO_IBRIDO.md` (diagnosi e piano originale) e `results/2026-09-22/RIEPILOGO_FINAL_V3.md` (numeri finali con IC 95%).

---

## 10. Configurazione attuale, con il perché di ogni valore

Da `config/rag_config.yaml`, con la ragione **reale** dietro ogni scelta (non quella storica):

| Parametro | Valore | Perché |
|---|---|---|
| `embedding.model_name` | `intfloat/multilingual-e5-small` | **cambiato il 21/09** da `paraphrase-multilingual-MiniLM-L12-v2`: finestra di 512 token invece di 128, elimina il troncamento (§11.1). Scelta di progetto, non su soglia numerica: nominalmente `paraphrase-multilingual + mmarco` aveva 2 domande in più su 30, differenza non significativa |
| `llm.temperature` | **0.1** | risposte quanto più deterministiche possibile |
| `retrieval.top_k` | 25 | con 10 alcuni chunk corretti non entravano mai fra i candidati |
| `retrieval.category_filter` | **false** | le 6 categorie non producibili dal classificatore delle query coprono il **75,8%** dei chunk indicizzati |
| `retrieval.hybrid_search.enabled` | **true** | **dal 21/09 ha effetto reale** (prima era dichiarato e non implementato, vedi §5): denso + BM25 nativo fusi con RRF. `false` per riprodurre il solo canale denso |
| `retrieval.hybrid_search.rrf_k` | 60 | costante di attenuazione della Reciprocal Rank Fusion, valore convenzionale |
| `retrieval.hybrid_search.dense_top_k` / `sparse_top_k` | 50 / 50 | candidati pescati da ciascun canale prima della fusione; il taglio a `top_k=25` avviene dopo, quindi la latenza del reranker non cambia |
| `retrieval.hybrid_search.bm25.k1` / `b` | 1.2 / 0.75 | valori convenzionali di Robertson e Zaragoza |
| `reranking.model` | `BAAI/bge-reranker-base` | confrontato con `mmarco-mMiniLMv2-L12-H384-v1` e `bge-reranker-v2-m3` su 30 domande (§9): nessuno supera la regola di adozione fissata a priori (guadagno ≥ 2 domande e latenza entro il doppio), quindi resta quello di partenza |
| `reranking.allow_fallback` | **false** | **nuovo dal 21/09**: se il modello non si carica il sistema si ferma invece di proseguire in silenzio senza reranking (era un degrado non visibile) |
| `reranking.top_k` | 5 | numero di documenti finali passati al LLM |
| `governance.pii_filter.enabled` | **false** | **nuovo dal 21/09**: il corpus è interamente pubblico, il filtro mascherava anche i contatti istituzionali del CNI senza proteggere nulla (vedi §11.9) |
| `chunking.chunk_size` / `overlap` | 1500 / 200 | pensato per dare contesto sufficiente al LLM |
| `crawler.included_paths` | 32 path | **ampliata il 21/09** da 5 a 32: i 5 originali restano invariati, aggiunti i percorsi già presenti nel corpus ma fuori dalla whitelist precedente (senza i quali una ingestion completa perderebbe il 36% degli URL) più `/area-cni` (schede provinciali, non ancora nel corpus: la prima ingestion con questa voce cambia la base di tutti i numeri) |
| `crawler` blocca `/en/` | — | 27% dei dati crawlati era in inglese, inutile per utenti italiani |
| `crawler.respect_robots_txt` | **true, ora applicato** | **corretto il 21/09**: era dichiarato ma il crawler non leggeva mai `robots.txt` |

---

## 11. Problemi noti e limiti tecnici confermati

Verificati in questa sessione contro il codice reale, non riportati per sentito dire.

### 11.1 Troncamento dell'embedding — **risolto il 21/09**

Il modello di embedding precedente aveva `max_seq_length = 128` token, contro
una mediana di **266 token** per chunk: l'**82,2%** dei chunk veniva troncato,
perdendo in media il 41,3% del contenuto. Risolto passando a
`intfloat/multilingual-e5-small` (finestra 512 token, §10): sul corpus attuale
solo **18 chunk su 13.784 (0,13%)** superano 512 token. La correzione da sola
(senza BM25) porta Hit@5 dal 40,0% al 46,7% — un miglioramento reale ma non
statisticamente significativo su n=30 (p=0,375); il grosso del guadagno viene
dal canale lessicale (§5, §9).

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
genera — rischio noto di bias di self-preference. La validazione umana in
cieco (§8), completata il 02-03/09 su tutte le 30 domande di `FINAL_V2`
(`results/report_judge_agreement.md`), **conferma empiricamente il
rischio, ma non uniformemente**: pertinenza (kappa 0,770) e correttezza
(kappa 0,674) hanno accordo sostanziale e sono utilizzabili con la
calibrazione nota (il giudice è ~1 punto più severo dell'umano sulla
correttezza); la fedeltà ha accordo sostanzialmente nullo (kappa -0,019)
e i suoi punteggi automatici non sono riportati come misura affidabile.

### 11.6 Duplicati EN/IT — risolto

Le pagine `/en/` sono ora bloccate dal crawler (§4.1) e uno script dedicato
(`scripts/purge_english_chunks.py`) rimuove i chunk inglesi già indicizzati.
Eseguito il 27/08 alle 16:02 (`results/purge_2026-08-27_16-02.json`): rimossi
**3.361 chunk** su 17.145 (pattern `/en/`), indice sceso a **13.784 chunk** —
il numero che compare da allora in `documents_indexed` nell'health check e in
tutti gli esperimenti successivi (ablation, `FINAL_V2`, oracle context,
confronto embedding). Motivo dichiarato nel log: allineamento dell'indice a
`CNICrawler.DENIED_PATTERNS`, introdotto il 2 luglio 2026 ma applicato solo
al crawl, non retroattivamente all'indice già esistente.

### 11.7 Pattern di categoria mancanti per la whitelist ampliata — **corretto il 23/09**

Vedi §4.3. `CATEGORY_PATTERNS` non copriva i nuovi percorsi aggiunti alla
whitelist del crawler il 21/09 (`/area-cni`, `/faq`, ecc.): sarebbero finiti su
`"generico"` o su una categoria decisa dal solo contenuto. Aggiunta in
`src/governance/public_data_filter.py` una mappa `WHITELIST_PATH_CATEGORIES`
(prefisso di path a segmento intero), consultata solo se nessun pattern
esistente corrisponde: nessun URL già categorizzato cambia categoria, cosa
verificata dai test in `tests/unit/test_categorie_e_indicizzazione.py`.
`/area-cni` → `organi`, trasparenza e `/images` residui → `documenti`, `/faq`
→ `servizi`, `/evidenza` e `/notizie-internazionali` → `news`. `/it/` resta di
proposito alla categoria dedotta dal contenuto. Nessun effetto sui risultati
riportati: vale dalla prossima ingestion.

### 11.8 Indicizzazione senza suddivisione a lotti — **corretto il 23/09**

`VectorIndexer.index_chunks()` (§4.8) costruisce tutti i `PointStruct` in
memoria e li invia a Qdrant in un'unica chiamata `client.upsert()`, senza
lotti — a differenza di `scripts/build_sparse_collection.py`, che spedisce a
gruppi di 256. Su un corpus di 13.784+ chunk (destinato a crescere con
`/area-cni`) questo può essere lento o pesante in memoria su una macchina con
8 GB condivisi. Corretto: `index_chunks()` invia ora lotti di 256 punti.
`avgdl` resta calcolata sull'intero corpus prima dell'invio, quindi i pesi BM25
sono identici a quelli di un invio unico (verificato da test).

### 11.9 Filtro PII mascherava i contatti dell'ente — **risolto il 21/09**

Scoperto durante le 90 valutazioni umane su `FINAL_V3`: `PIIFilter` (§6)
mascherava email e telefono su **tutto** il prompt passato al generatore,
contesto incluso — non solo l'input dell'utente. Rendeva impossibili due
domande del golden dataset: Q06 (contatti del CNI: telefono/email/PEC nel
contesto, ma oscurati) e Q12 (il codice fiscale, un numero di 11 cifre, letto
come telefono dalla stessa regex). Risolto rendendo il filtro configurabile e
disattivandolo (`governance.pii_filter.enabled: false`, §10): il corpus è
interamente pubblico, non c'è nulla da proteggere. Le due domande sono state
rilanciate con il filtro spento e le risposte riannotate; il run `FINAL_V2`
resta con il filtro attivo (Q06 lì era classificata `generation_miss`, causa
in realtà il filtro, non il generatore).

### 11.10 Pulsante "Indicizza Dati" senza conferma sufficiente — **corretto il 23/09**

Il pulsante nel menu impostazioni del frontend (`POST /api/v1/ingest`) cancella
**incondizionatamente** la collection in produzione e rilancia un crawl
completo da zero, senza backup automatico. Dal 21/09 c'è una conferma
esplicita nel browser prima di procedere (verificato: se rifiutata, nessuna
richiesta parte), ma restano due limiti non ancora corretti, deliberatamente
rimandati su richiesta esplicita:
1. nessun pattern di categoria per i nuovi percorsi (§11.7);
2. scrive ancora sulla collection di produzione invece che su una nuova — un
   clic confermato distruggerebbe l'indice su cui sono validati `FINAL_V3` e
   le 90 valutazioni umane, recuperabile solo dal backup manuale in
   `data/qdrant_db.backup_2026-09-22/` (non tracciato da git, solo locale).

**Correzione del 23/09.** Entrambi i limiti sono chiusi: il primo con §11.7;
il secondo facendo scrivere `POST /api/v1/ingest` su una collection nuova,
`<collection in uso>_ingest_<AAAAMMGG_HHMMSS>`, senza mai cancellare o
modificare quella di produzione. Il messaggio di fine indicizzazione indica
il nome della collection creata e il testo della conferma nel frontend è stato
aggiornato di conseguenza. Gli
script da riga di comando (`scripts/run_ingestion.py`, `scripts/build_index.py`)
con `--clear` continuano invece a ricostruire la collection configurata: sono
un'operazione deliberata, non un clic.

**Scelta della collection dal frontend (23/09).** La sezione *Collection* del
menu impostazioni elenca le collection presenti con il numero di chunk e
permette di attivarne una (`PUT /collections/active`), con conferma. Il cambio:
- vale subito per chat, statistiche, health check e nuovi run di valutazione:
  retriever e indicizzatore leggono la collection attiva a ogni chiamata, non
  una copia presa all'avvio;
- è scritto in `config/qdrant_config.yaml` (solo la riga `collection_name`,
  commenti intatti): il file resta l'unica fonte della configurazione, niente
  override nascosti come quello del modello di embedding (§11.5);
- è rifiutato per collection senza vettore BM25 o con dimensione diversa da
  quella del modello di embedding in uso, e durante un'indicizzazione;
- non cancella nulla: si torna alla collection precedente dallo stesso menu.

Da questa data ogni run di `run_evaluation.py` registra la collection
interrogata (campo `collection`, esposto da `/evaluation/runs` e
`/evaluation/latest`); i run precedenti non la riportano. Test in
`tests/unit/test_selezione_collection.py`, compresa una prova completa del flusso
di `POST /ingest` con crawler ed embedding simulati.

### 11.11 Su Windows la cancellazione di una collection locale non svuotava i dati — **corretto il 23/09**

Qdrant in modalità locale cancella la cartella di una collection senza chiuderne
prima il file SQLite. Su Windows un file aperto non si cancella: l'errore è
ignorato (`rmtree` con `ignore_errors=True`) e la collection ricreata con lo
stesso nome riapre i vecchi punti. Colpiva `clear_index()`, cioè gli script
`run_ingestion.py` e `build_index.py` con `--clear`, che su Windows non
svuotavano la collection e duplicavano i chunk. Non colpiva il pulsante
"Indicizza Dati" (crea sempre una collection con nome nuovo) né Linux e macOS.
Emerso eseguendo `pytest` su Windows; corretto in
`QdrantClientManager.delete_collection`, che ora chiude il file prima di
cancellare (PR #11), con un test che ne controlla la causa su ogni sistema.

---

## 12. Stato del progetto al 23/09/2026 e cosa manca

**Aggiornamento 24/09 — dashboard e chat.** Pagina Statistiche riorganizzata
senza dati ripetuti (§8), domande suggerite della chat sostituite con quelle
verificate dall'annotazione umana (§8). Solo frontend: nessun effetto su
configurazione, risultati o numeri della tesi.

**Aggiornamento 23/09 — versione finale congelata su `main`** (PR #8-#11, tag
`congelato-2026-09-23` su `8f3f422`): chiusi i limiti §11.7, §11.8 e §11.10,
aggiunta la scelta della collection attiva dal frontend, corretta la
cancellazione delle collection su Windows (§11.11). La configurazione in
`config/` è identica a quella del run `FINAL_V3`: numeri e annotazioni restano
validi. Da qui il lavoro prosegue solo sulla tesi.

**Aggiornamento 21-22/09 — recupero ibrido, dalla diagnosi alla tesi:**
- Diagnosticato che in 13 domande fallite su 14 la fonte non entrava fra i
  candidati densi, e il termine richiesto era quasi sempre lessicale (nomi,
  codici, date) — un embedding non ha un intorno semantico per `80057570584`.
- Implementato e adottato il recupero ibrido: BM25 nativo in Qdrant (vettore
  sparso con modificatore IDF) fuso col canale denso via Reciprocal Rank
  Fusion, in un'unica chiamata (§5, §10).
- Scoperta e corretta una configurazione di produzione mai dichiarata: il
  modello di embedding reale era `all-MiniLM-L6-v2` (inglese), non quello nel
  YAML — una variabile d'ambiente lo sovrascriveva in silenzio (§11.5,
  `ModelFactory.resolve_embedding_model()`).
- Confrontati 3 modelli di embedding × con/senza BM25 (6 configurazioni) e 3
  reranker, tutti sulle stesse 30 domande — matrice completa in
  `/evaluation/ablation-matrix` e nella dashboard (§7, §8).
- Congelata la configurazione finale (tag `congelato-2026-09-21-e5`), eseguito
  il run end-to-end `FINAL_V3`, completate le 90 valutazioni umane (30
  domande × 3 assi), corrette 4 annotazioni dopo verifica sui dati grezzi.
- Scoperto e corretto il filtro PII che mascherava i contatti dell'ente
  (§11.9); due domande rilanciate col filtro spento.
- Costruito il run definitivo `eval_FINAL_V3_DEFINITIVO.json` unendo le due
  esecuzioni, con confronto appaiato completo contro `FINAL_V2` (§9).
- Dashboard aggiornata: configurazione del run, confronto con FINAL_V2,
  matrice di ablation, confronto per domanda (§8).
- README aggiornato con setup Windows testato via lettura del codice (nessun
  percorso Unix hardcoded); `run.ps1` corretto (citava LM Studio invece di
  Ollama, e pulsanti VS Code mai creati).
- Trovati e corretti 6 difetti non legati direttamente al recupero: la
  pipeline di indicizzazione produceva un formato di collection non
  interrogabile dal nuovo retriever; il reranker degradava in silenzio se il
  modello non si caricava; il crawler non applicava `robots.txt` pur
  dichiarandolo; uno script CLI non partiva per un nome non importato;
  un'eccezione nel controllo di salute veniva inghiottita; `.env.example`
  elencava dieci variabili mai lette dal codice.

**Da fare, in ordine di priorità** (aggiornato al 23/09):
1. ~~Pattern di categoria per i nuovi percorsi della whitelist~~ — fatto il 23/09 (§11.7).
2. ~~Indicizzazione a lotti invece di un unico upsert~~ — fatto il 23/09 (§11.8).
3. ~~Pulsante "Indicizza Dati": scrivere su una collection nuova~~ — fatto il 23/09 (§11.10).
4. ~~Pulizia finale: rimuovere l'implementazione BM25 in memoria~~ — confermata il 23/09. Verificato che il codice attivo non la contiene più: `src/rag/sparse_index.py`, `src/rag/fusion.py` e `tests/unit/test_sparse_e_fusione.py` esistono solo sul branch `feature/recupero-ibrido`, lasciato com'è: non è usato da nulla e non dà fastidio. Si conserva il tag `sperimentazione-recupero-ibrido` (stesso commit `fa6d0aa`): la matrice a 6 configurazioni riportata in tesi è stata misurata con quell'implementazione e il tag la rende riproducibile. I riferimenti rimasti nel codice attivo sono solo commenti che documentano l'equivalenza nativo/in memoria.
5. ~~Unione di `release/recupero-ibrido` su `main`~~ — risulta fatta: al 23/09 `main` contiene tutti i commit di `release/recupero-ibrido`. Testo originale: unione **solo con conferma esplicita**: `main` resta la configurazione precedente finché non arriva quel via libera. Backup del `main` precedente in `backup/main-2026-09-21`.

**Cosa manca per la tesi:** aggiornare abstract, introduzione e i capitoli con
i nuovi numeri — la tabella completa è in `results/2026-09-22/RIEPILOGO_FINAL_V3.md`.
Dichiarare esplicitamente in tesi: (a) `FINAL_V2` girava con un modello di
embedding diverso da quello dichiarato; (b) la matrice a 6 configurazioni è
stata misurata con un'implementazione in memoria del BM25, verificata
equivalente a quella nativa adottata in produzione (punteggi entro 6·10⁻⁸,
stessi risultati sulle 30 domande); (c) `/area-cni` resta fuori dal corpus,
configurata solo per la prossima ingestion.

---

## 12-bis. Stato del progetto al 03/09/2026 (archiviato)

Sezione precedente, lasciata per riferimento storico — superata dal §12 sopra.

**Fatto e verificato:**
- Fix del blocco dell'event loop su `/query` (§11.2) — pushato, verificato con `pytest` (24/24 test passano)
- Fix reale in produzione: `CitationBuilder.build()` troncava sempre a 1 citazione (`return citations[:1]`) — corretto, ora restituisce l'elenco completo (commit `1bb0ba1`)
- Tutti e quattro gli esperimenti pianificati sono stati eseguiti su n=30 (`golden_dataset_v2.json`): ablation study, valutazione end-to-end (`FINAL_V2`), test a contesto oracolo, confronto fra modelli di embedding — ciascuno con un report dedicato in `results/report_*.md` e una spiegazione discorsiva in `doc/GUIDA_ESPERIMENTI.md`
- Bug scoperto e corretto in `compare_embeddings.py`: il modello "attuale" veniva interrogato con `SentenceTransformer(...).encode()` invece di `ModelFactory.create_embeddings()`, producendo vettori incoerenti con l'indice e un MRR baseline artificialmente basso (0,17 invece di 0,294) — rieseguito dopo il fix, numeri coerenti con `FINAL_V2`
- Verificata la correttezza di `metrics.py` e `stats.py` (le formule che producono i numeri della tesi)
- Documentato il troncamento dell'embedding (§11.1): 128 token max, mediana chunk 266 token, 82,2% dei chunk troncati — riportato come limite dichiarato in `CONCLUSIONI_TESI.md`, non ancora corretto in produzione (cambio di modello valutato e rimandato, vedi sotto)
- Documentato il purge dei chunk inglesi (§11.6): 17.145 → 13.784 chunk, 27/08
- `doc/SISTEMA.md`, `doc/GUIDA_ESPERIMENTI.md`, `doc/NOTE_CAP1_CAP2.md`, `doc/CONCLUSIONI_TESI.md` creati come materiale di riferimento consolidato
- **Validazione umana in cieco completata** (02-03/09) su tutte le 30 domande di `FINAL_V2` — `results/annotations_FINAL_V2.json`, `results/report_judge_agreement.md`. Risultato: giudice automatico utilizzabile per pertinenza (kappa 0,770) e correttezza (kappa 0,674, con bias -0,966 punti da correggere), non per fedeltà (kappa -0,019). Un secondo caso concreto emerso durante l'annotazione (Q01, presidente CNI: il generatore ha risposto "Armando Zambrano" invece di "Angelo Domenico Perrini") ha confermato via ricerca diretta nell'indice (`/qdrant`) che l'informazione corretta è nel corpus ma non è mai stata recuperata — `retrieval_miss` verificato, non un'allucinazione da fonte assente

**Deliberatamente rimandato (non necessario per rispondere alla domanda di ricerca, tempo limitato fino al 13/10):**
- Cambio del modello di embedding in produzione (`e5-small` mostra risultati migliori ma non statisticamente significativi su n=30, vedi `report_compare_embeddings.md`) + re-indicizzazione + nuova valutazione completa
- `benchmarks/compare_generators.py`: script pronto, mai eseguito (vedi §9)
- `config/holdout_v1.json`: scaffold quasi vuoto (solo H01 compilata per intero, H02-H10 hanno solo il testo della domanda), mai eseguito (vedi §9)
- Confronto con un modello cloud (es. API Claude) sulle domande di tipo `generation_miss`

**Cosa manca:**

Nessun'altra attività tecnica è necessaria per rispondere alla domanda di
ricerca — il progetto è chiuso lato esperimenti e dati. Resta solo:

1. **Scrittura dei capitoli 1-4 della tesi** — materiale di riferimento pronto in `doc/NOTE_CAP1_CAP2.md`, `doc/SISTEMA.md`, `doc/GUIDA_ESPERIMENTI.md`, `doc/CONCLUSIONI_TESI.md` (quest'ultimo con tutti i numeri reali, nessun placeholder `[X]` residuo).
2. Citare i punti deliberatamente rimandati sopra come "sviluppi futuri" nel capitolo delle conclusioni — già presente come paragrafo nei Limiti di `doc/CONCLUSIONI_TESI.md`.

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

**La tesi è a 6 capitoli** (`doc/INDICE_TESI.md` su `origin/main`, non gli 8
di versioni precedenti di questo indice): capitoli 1-2 descrivono il sistema,
3-5 lo misurano e discutono i limiti, 6 conclude.

| Sezione di questo documento | Capitolo tesi |
|---|---|
| §2 Stack tecnologico | Cap. 2 (§2.2 lo stack) |
| §3-§8 Architettura, ingestion, RAG, governance, API, frontend | Cap. 2 (§2.4-§2.9 architettura e implementazione) |
| §5 recupero ibrido, §10 configurazione | Cap. 2 §2.6 (pipeline RAG) e Cap. 4 §4.2 (ablation) |
| §9 Valutazione e benchmarking | Cap. 3 (metodologia della valutazione) |
| Risultati prodotti da §9, matrice di ablation | Cap. 4 (risultati) |
| §11 Problemi noti | Cap. 5 (discussione, minacce alla validità, limiti dichiarati) |
| §11.7, §11.8, §11.10 (limiti ancora aperti) | Cap. 6 (conclusioni e sviluppi futuri) |
| §12 (l'intervento sul recupero, da diagnosi a numeri) | Cap. 6 §6.2 — non più "non implementata": va riscritta come intervento applicato e misurato |
