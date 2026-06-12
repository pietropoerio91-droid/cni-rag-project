# Documentazione del Progetto RAG per il CNI

**Titolo:** Architettura RAG per l'estrazione e la consultazione intelligente dei dati pubblici del Consiglio Nazionale degli Ingegneri  
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`  
**Branch:** `feature/indicizzazione`

---

## Indice

1. [Architettura Generale](#1-architettura-generale)
2. [Struttura del Progetto](#2-struttura-del-progetto)
3. [Modulo Core](#3-modulo-core)
4. [Modulo Governance](#4-modulo-governance)
5. [Modulo Ingestion](#5-modulo-ingestion)
6. [Modulo Vector Store](#6-modulo-vector-store)
7. [Modulo RAG](#7-modulo-rag)
8. [Modulo Inference](#8-modulo-inference)
9. [Modulo API](#9-modulo-api)
10. [Scripts](#10-scripts)
11. [Frontend Angular](#11-frontend-angular)
12. [Benchmarking](#12-benchmarking)
13. [Notebooks](#13-notebooks)
14. [Test](#14-test)
15. [Configurazione](#15-configurazione)
16. [Docker](#16-docker)
17. [Flusso di Esecuzione](#17-flusso-di-esecuzione)

---

## 1. Architettura Generale

Il sistema implementa un'architettura RAG (Retrieval-Augmented Generation) completa, composta da:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CNI RAG System                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  FASE 1: INGESTION                                                   │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │Crawler  │→│Downloader│→│Parser    │→│Cleaner   │→│Chunker │ │
│  │(httpx)  │  │(JSON)    │  │(trafila) │  │(regex)   │  │(LC)    │ │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘  └────┬───┘ │
│                                                               │      │
│  FASE 2: VECTORIZATION                                         │      │
│                                          ┌──────────┐         │      │
│                                   ←──────│ Embedder │←────────┘      │
│                                   │      │(MiniLM)  │               │
│                                   │      └────┬─────┘               │
│                                   │           │                     │
│  FASE 3: INDEXING                   │           │                     │
│                                   │      ┌────▼─────┐               │
│                                   └──────│ Indexer  │               │
│                                          │ (Qdrant) │               │
│                                          └──────────┘               │
│                                                                      │
│  FASE 4: QUERY                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │Classifier│→│Retriever │→│Reranker  │→│Prompt    │→│LLM     │ │
│  │(keyword) │  │(hybrid)  │  │(cross-  │  │Builder   │  │(Llama) │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tecnologie Utilizzate

| Componente | Tecnologia | Ruolo |
|---|---|---|
| Backend | Python 3.11+ + FastAPI | API server |
| Frontend | Angular 18 | Interfaccia utente |
| LLM | Llama 3.2 via LM Studio | Generazione risposte |
| Embeddings | all-MiniLM-L6-v2 | Vettorizzazione testo |
| Vector Store | Qdrant (locale) | Database vettoriale |
| Orchestratore | LangGraph | Pipeline RAG |
| Framework RAG | LangChain | Chunking, prompt |
| Documenti | httpx + BeautifulSoup + trafilatura | Crawling e parsing |

---

## 2. Struttura del Progetto

```
cni-rag-project/
├── .env.example                 # Template variabili d'ambiente
├── .gitignore                   # File ignorati da git
├── Dockerfile                   # Build dell'immagine Docker
├── README.md                    # Readme del progetto
├── docker-compose.yml           # Orchestrazione Docker
├── requirements.txt             # Dipendenze Python
│
├── benchmarks/                  # Benchmarking
│   └── run_benchmark.py         # Suite di benchmark con metriche IR
│
├── config/                      # Configurazioni YAML
│   ├── logging_config.yaml      # Config logging
│   ├── model_config.yaml        # Config modelli (LLM, embeddings)
│   ├── qdrant_config.yaml       # Config Qdrant
│   └── rag_config.yaml          # Config RAG pipeline
│
├── data/                        # Dati (gitignorati)
│   ├── raw/                     # Documenti crawlti grezzi (JSON)
│   ├── processed/               # Documenti processati
│   ├── chunks/                  # Chunk testuali
│   └── qdrant_db/               # Database vettoriale Qdrant
│
├── frontend/                    # Applicazione Angular
│   ├── angular.json
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.html
│       ├── main.ts
│       ├── styles.css
│       └── app/
│           ├── app.component.ts
│           ├── app.config.ts
│           ├── components/
│           │   └── chat/
│           │       └── chat.component.ts
│           ├── models/
│           │   └── rag.models.ts
│           └── services/
│               └── rag.service.ts
│
├── notebooks/                   # Jupyter Notebooks
│   ├── 01_analisi_esplorativa_dati_cni.ipynb
│   └── 02_demo_tesi_relatore.ipynb
│
├── scripts/                     # Script CLI eseguibili
│   ├── build_index.py           # Ricostruzione indice vettoriale
│   ├── run_api.py               # Avvio server API
│   ├── run_crawler.py           # Crawl del sito CNI
│   └── run_ingestion.py         # Pipeline completa di ingestion
│
├── src/                         # Codice sorgente principale
│   ├── __init__.py
│   ├── api/                     # FastAPI endpoints
│   │   ├── main.py              # App FastAPI con CORS
│   │   ├── routes.py            # Endpoint: query, stream, ingest, health
│   │   └── schemas.py           # Pydantic models
│   │
│   ├── core/                    # Moduli core
│   │   ├── config_loader.py     # Caricamento configurazioni YAML
│   │   ├── logging.py           # Setup logging
│   │   └── model_factory.py     # Factory per LLM e embeddings
│   │
│   ├── governance/              # Modulo governance
│   │   ├── monitoring.py        # Tracciamento richieste
│   │   ├── pii_filter.py        # Filtro dati sensibili
│   │   ├── public_data_filter.py # Filtro dati pubblici
│   │   └── quality_check.py     # Controllo qualità contenuti
│   │
│   ├── inference/               # Modulo inferenza
│   │   ├── citation_builder.py  # Costruzione citazioni
│   │   ├── llm_client.py        # Client LLM (LM Studio)
│   │   └── response_generator.py # Generazione risposte
│   │
│   ├── ingestion/               # Modulo ingestion
│   │   ├── chunker.py           # Suddivisione in chunk
│   │   ├── cleaner.py           # Pulizia testo
│   │   ├── crawler.py           # Crawler sito CNI
│   │   ├── downloader.py        # Salvataggio documenti
│   │   ├── embedder.py          # Generazione embeddings
│   │   └── parser.py            # Parsing HTML/PDF
│   │
│   ├── rag/                     # Modulo RAG
│   │   ├── hybrid_retriever.py  # Retrieval ibrido
│   │   ├── prompt_builder.py    # Costruzione prompt
│   │   ├── query_classifier.py  # Classificazione query
│   │   ├── rag_chain.py         # Orchestrazione LangGraph
│   │   └── reranker.py          # Riordinamento risultati
│   │
│   └── vectorstore/             # Modulo vector store
│       ├── indexer.py           # Indicizzazione vettori
│       ├── qdrant_client.py     # Client Qdrant
│       └── retriever.py         # Retrieval vettoriale
│
└── tests/                       # Test
    ├── conftest.py
    ├── integration/
    │   ├── test_ingestion_pipeline.py
    │   └── test_rag_pipeline.py
    └── unit/
        ├── test_chunker.py
        └── test_retriever.py
```

---

## 3. Modulo Core

### `src/core/config_loader.py`

Carica i file YAML dalla directory `config/` con caching singleton.

**Classi:**
- `ConfigLoader` — metodi statici per caricare ogni configurazione:
  - `load(nome)` → carica e cache qualsiasi YAML
  - `get_rag_config()` → configurazione RAG
  - `get_model_config()` → configurazione modelli
  - `get_qdrant_config()` → configurazione Qdrant
  - `get_logging_config()` → configurazione logging

### `src/core/logging.py`

Configura il logging usando il file YAML o fallback a basicConfig.

**Funzioni:**
- `setup_logging(config_path?)` → inizzializza logging

### `src/core/model_factory.py`

Factory pattern per creare modelli LLM e di embedding.

**Classi:**
- `ModelFactory` — metodi statici:
  - `create_embeddings()` → HuggingFaceEmbeddings (all-MiniLM-L6-v2)
  - `create_llm()` → LLM da LM Studio (ChatOpenAI) o LlamaCpp

**Provider supportati:**
- `lm_studio` → ChatOpenAI su `http://localhost:1234/v1`
- `llama_cpp` → LlamaCpp da file locale

---

## 4. Modulo Governance

### `src/governance/pii_filter.py`

Filtra dati sensibili dal testo (email, telefono, codice fiscale, partita IVA, SSN).

**Pattern regex:**
- Email: `[\w.%-]+@[\w.-]+\.[a-zA-Z]{2,}`
- Telefono: numeri con prefisso
- Codice Fiscale: formato italiano `ABCDEF12G34H567I`
- Partita IVA: `IT` + 11 cifre
- SSN: formato americano

**Opzioni:**
- `enabled` — attiva/disattiva filtro
- `masked` — sostituisce con `[EMAIL_REDACTED]` o rimuove

### `src/governance/public_data_filter.py`

Verifica se un URL/contenuto è pubblico e categorizza.

**Metodi:**
- `is_public(url, content)` → True se il contenuto è pubblico
- `categorize(url, content)` → assegna categoria (normativa, organi, ecc.)

**Blocca:**
- Path `/wp-admin`, `/private`, `/restricted`
- Keyword: password, riservato, confidenziale, ecc.

### `src/governance/quality_check.py`

Verifica la qualità del contenuto testuale.

**Controlli:**
- Lunghezza minima (default: 50 caratteri)
- Lunghezza massima (default: 100000 caratteri)
- Repetition ratio (default: max 0.3)
- Lingua richiesta (default: italiano)

### `src/governance/monitoring.py`

Tracciamento delle richieste RAG con timing.

**Metodi:**
- `start_trace()` → inizia una traccia
- `log_event()` → registra evento
- `end_trace()` → termina e calcola durata

---

## 5. Modulo Ingestion

### `src/ingestion/crawler.py` — `CNICrawler`

Crawler asincrono del sito CNI basato su `httpx` + `BeautifulSoup`.

**Configurazione** (da `rag_config.yaml`):
- `base_url`: https://www.cni.it
- `max_depth`: 3 livelli
- `max_pages`: 100 pagine
- `delay`: 1 secondo tra richieste
- `allowed_domains`: www.cni.it, cni.it
- `included_paths`: /chi-siamo, /organi, /commissioni, ecc.

**Flusso:**
1. GET della pagina HTML
2. Estrazione link <a href>
3. Parsing HTML per estrarre testo
4. Parsing PDF con PyMuPDF
5. Visita ricorsiva con controllo profondità
6. Salva in self.results come dict

**Output:** `list[dict]` con `{url, title, content, meta}`

### `src/ingestion/downloader.py` — `Downloader`

Salva/carica documenti come JSON su disco.

**Metodi:**
- `save_document(dict)` → salva in `data/raw/{safe_name}.json`
- `save_documents(list)` → batch save
- `load_documents()` → carica tutti i JSON da directory

### `src/ingestion/parser.py` — `DocumentParser`

Parsing di HTML e PDF.

**Metodi:**
- `parse_html(html, url)` → usa trafilatura, fallback regex
- `parse_pdf_text(text)` → pulisce testo PDF

### `src/ingestion/cleaner.py` — `TextCleaner`

Pulisce il testo da boilerplate.

**Pattern rimossi:**
- © e diritti riservati
- Cookie Policy, Privacy Policy
- "Seguici su", "Condividi su"
- Righe vuote consecutive

**Metodi:**
- `_remove_boilerplate(text)` → regex
- `_normalize_whitespace(text)` → spazi uniformi
- `_remove_repeated_lines(text)` → righe duplicate

### `src/ingestion/chunker.py` — `DocumentChunker`

Suddivide documenti in chunk usando `RecursiveCharacterTextSplitter` di LangChain.

**Configurazione** (da `rag_config.yaml`):
- `chunk_size`: 512 caratteri
- `chunk_overlap`: 64 caratteri
- `separators`: ["\n\n", "\n", ".", " ", ""]

**Output chunk:** `{content, metadata: {source, title, chunk_index, total_chunks}}`

### `src/ingestion/embedder.py` — `EmbeddingGenerator`

Genera embeddings vettoriali usando `sentence-transformers`.

**Metodi:**
- `generate(text)` → embedding singolo
- `generate_batch(texts)` → batch embedding
- `process_chunks(chunks)` → aggiunge campo `embedding` a ogni chunk

---

## 6. Modulo Vector Store

### `src/vectorstore/qdrant_client.py` — `QdrantClientManager`

Gestisce connessione a Qdrant (locale o remoto).

**Modalità:**
- `local` → salva su `./data/qdrant_db`
- `remote` → connessione a host:port

**All'avvio:**
1. Crea directory se locale
2. Connette a Qdrant
3. Crea collezione se non esiste
4. Configura: Cosine distance, dimensione 384, HNSW index

### `src/vectorstore/indexer.py` — `VectorIndexer`

Indicizza chunk vettorizzati in Qdrant.

**Metodi:**
- `index_chunks(chunks)` → upsert con UUID, embedding + payload
- `count_points()` → conta punti nella collezione
- `clear_index()` → cancella e ricrea collezione

### `src/vectorstore/retriever.py` — `VectorRetriever`

Recupera documenti simili da Qdrant.

**Metodi:**
- `retrieve(query, top_k, filter_condition)` → search vettoriale
- `retrieve_by_category(query, category)` → filtro per categoria
- `hybrid_retrieve(query, top_k)` → alias

**Configurazione:**
- `top_k`: 5
- `score_threshold`: 0.5

---

## 7. Modulo RAG

### `src/rag/query_classifier.py` — `QueryClassifier`

Classifica la query dell'utente in una categoria basata su keyword matching.

**Categorie:**
| Categoria | Keyword |
|---|---|
| normativa | normativa, legge, decreto, regolamento, codice, articolo |
| organi | organo, consiglio, presidente, vicepresidente, segretario, tesoriere |
| commissioni | commissione, comitato, gruppo, tavolo |
| albo | albo, elenco, iscrizione, registro, ingegnere, professione |
| formazione | formazione, credito, cfp, corso, aggiornamento, seminario |
| servizi | servizio, sportello, assistenza, modello, domanda |
| documenti | documento, bilancio, relazione, verbale, delibera |
| contatti | contatto, sede, telefono, email, pec, indirizzo |
| generico | (nessuna corrispondenza) |

### `src/rag/hybrid_retriever.py` — `HybridRetriever`

Combina classificazione query + retrieval vettoriale.

**Flusso:**
1. Classifica query
2. Applica filtro categoria se non generico
3. Chiama VectorRetriever.retrieve()

### `src/rag/reranker.py` — `Reranker`

Riordina i risultati retrieved usando un cross-encoder.

**Configurazione:**
- `enabled`: true
- `top_k`: 3
- `model`: cross-encoder/ms-marco-MiniLM-L-6-v2

**Fallback:** Se cross-encoder non disponibile, ordina per score vettoriale.

### `src/rag/prompt_builder.py` — `PromptBuilder`

Costruisce il prompt per il LLM.

**Template system:**
```
Sei un assistente specializzato nella consultazione dei dati pubblici del CNI.
Utilizza SOLO i documenti forniti nel contesto per rispondere.

Documenti di riferimento:
[Documento 1 - Titolo]
Fonte: URL
Contenuto...

Domanda: {question}
```

**Metodi:**
- `build_prompt(question, results)` → lista messaggi (system + user)
- `build_stream_prompt(question, results)` → stringa per streaming

### `src/rag/rag_chain.py` — `RAGChain`

Orchestrazione completa del flusso RAG con LangGraph.

**Grafo LangGraph:**

```
classify ──► retrieve ──► rerank ──► build_prompt ──► generate ──► build_citations ──► END
```

**Nodi:**
1. **classify** → QueryClassifier.classify(query)
2. **retrieve** → HybridRetriever.retrieve(query)
3. **rerank** → Reranker.rerank(query, docs)
4. **build_prompt** → PromptBuilder.build_prompt(question, docs)
5. **generate** → PIIFilter → ResponseGenerator.generate(prompt)
6. **build_citations** → CitationBuilder.build(docs, response)

**Stato (RAGState):**
```python
{
    "question": str,
    "category": str,
    "retrieved_docs": list,
    "reranked_docs": list,
    "prompt": list,
    "response": str,
    "citations": list,
    "trace_id": str,
}
```

**Metodi pubblici:**
- `query(question)` → esecuzione sincrona
- `astream(question)` → generator asincrono per streaming SSE

---

## 8. Modulo Inference

### `src/inference/llm_client.py` — `LLMClient`

Wrapper per chiamate al LLM tramite LangChain.

**Metodi:**
- `invoke(messages)` → chiamata sincrona
- `ainvoke(messages)` → chiamata asincrona
- `stream(messages)` → streaming token per token

**Conversione messaggi:**
Da formato `{role, content}` a `SystemMessage`/`HumanMessage` LangChain.

### `src/inference/response_generator.py` — `ResponseGenerator`

Genera risposte dal LLM in modalità sincrona, asincrona e streaming.

**Metodi:**
- `generate(messages)` → risposta completa
- `agenerate(messages)` → risposta asincrona
- `astream_generate(prompt)` → streaming async

### `src/inference/citation_builder.py` — `CitationBuilder`

Costruisce citazioni dai documenti usati per generare la risposta.

**Output:** `list[dict]` con:
- `title`: titolo del documento
- `source`: URL
- `relevance_score`: score
- `excerpt`: estratto (200 caratteri)

---

## 9. Modulo API

### `src/api/schemas.py` — Pydantic Models

**Request:**
- `QueryRequest`: `{question: str (1-2000), top_k?: int (1-20)}`

**Response:**
- `QueryResponse`: `{response, citations[], category, trace_id}`
- `CitationResponse`: `{title, source, relevance_score, excerpt}`
- `HealthResponse`: `{status, version, documents_indexed, llm_connected}`
- `IngestResponse`: `{status, documents_crawled, chunks_indexed, message}`
- `ErrorResponse`: `{detail, code}`

### `src/api/routes.py` — FastAPI Router

**Endpoint:**

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/v1/query` | Query RAG standard |
| POST | `/api/v1/query/stream` | Query in streaming SSE |
| GET | `/api/v1/health` | Stato del sistema |
| POST | `/api/v1/ingest` | Crawl e indicizzazione |

**Dettaglio endpoint:**

**POST /api/v1/query**
```json
// Request
{"question": "Quali sono gli organi del CNI?"}
// Response
{
  "response": "Il Consiglio Nazionale degli Ingegneri è composto da...",
  "citations": [
    {"title": "Organi CNI", "source": "https://www.cni.it/organi", "relevance_score": 0.95, "excerpt": "..."}
  ],
  "category": "organi",
  "trace_id": "uuid"
}
```

**POST /api/v1/query/stream**
Streaming SSE con eventi:
- `type: metadata` → categoria e fonti
- `type: chunk` → token della risposta
- `type: done` → citazioni finali

**GET /api/v1/health**
```json
{"status": "ok", "version": "0.1.0", "documents_indexed": 42, "llm_connected": true}
```

**POST /api/v1/ingest**
Esegue l'intera pipeline di ingestion e restituisce riepilogo.

### `src/api/main.py` — FastAPI App

- CORS configurato per `http://localhost:4200`
- Prefix `/api/v1`
- Middleware: CORS, logging startup/shutdown

---

## 10. Scripts

### `scripts/run_crawler.py`

Crawl del sito CNI.

**Opzioni CLI:**
- `--max-pages` (default: 100)
- `--max-depth` (default: 3)
- `--output` (default: data/raw)
- `--delay` (default: 1.0)

### `scripts/run_ingestion.py`

Pipeline completa di ingestion.

**Opzioni CLI:**
- `--crawl/--no-crawl` (default: crawl)
- `--max-pages` (default: 100)
- `--input` (default: data/raw)

**Fasi:**
1. Crawl (o caricamento da disco)
2. Filtro dati pubblici
3. Quality check
4. Clean
5. Chunking
6. Embedding (con barra di progresso)
7. Indicizzazione Qdrant

### `scripts/build_index.py`

Ricostruzione indice da documenti processati.

**Opzioni CLI:**
- `--input` (default: data/processed)
- `--clear/--no-clear` (default: no-clear)

### `scripts/run_api.py`

Avvia il server API.

**Opzioni CLI:**
- `--host` (default: 0.0.0.0)
- `--port` (default: 8000)
- `--reload/--no-reload` (default: reload)

---

## 11. Frontend Angular

### `frontend/src/app/components/chat/chat.component.ts`

Componente chat interattiva standalone.

**Funzionalità:**
- Area messaggi con storico
- Input text con invio tramite Enter
- Suggerimenti di domande predefinite
- Pulsante check health (LED verde/rosso)
- Pulsante indicizzazione dati
- Indicatore di digitazione
- Citazioni cliccabili
- Gestione errori

**Stati:**
- `welcome` → schermata iniziale con suggerimenti
- `loading` → animazione typing
- `response` → messaggio con citazioni
- `error` → messaggio di errore in rosso

### `frontend/src/app/services/rag.service.ts`

Servizio HTTP per comunicare con la API.

**Metodi:**
- `query(request)` → POST `/api/v1/query`
- `health()` → GET `/api/v1/health`
- `ingest()` → POST `/api/v1/ingest`

**Streaming:** Implementa EventSource polyfill con XHR per lo streaming SSE.

### `frontend/src/app/models/rag.models.ts`

Interfacce TypeScript:
- `Citation`, `QueryResponse`, `QueryRequest`
- `HealthResponse`, `IngestResponse`
- `ChatMessage`, `StreamEvent`

### `frontend/src/app/app.component.ts`

Componente root con header e status LED.

---

## 12. Benchmarking

### `benchmarks/run_benchmark.py`

Suite di benchmark per valutare diverse configurazioni del sistema RAG.

**Metriche implementate:**

| Metrica | Formula | Descrizione |
|---|---|---|
| **MRR** | `1/N * Σ(1/rankᵢ)` | Mean Reciprocal Rank — quanto in alto arriva il primo risultato rilevante |
| **Recall@1** | `relevant@1 / N` | Frazione di query con primo risultato rilevante |
| **Recall@3** | `relevant@3 / N` | Frazione di query con risultato rilevante nei top 3 |
| **Recall@5** | `relevant@5 / N` | Frazione di query con risultato rilevante nei top 5 |
| **Precision@1** | `(top1 relevante) / N` | Precisione al primo risultato |
| **Precision@3** | `Σ(relevant@3/3) / N` | Precisione media nei top 3 |
| **Classification Accuracy** | `corrette / N` | Accuratezza classificazione categoria |

**Configurazioni testate automaticamente:**

| Nome | chunk_size | overlap | top_k | Reranker | Note |
|---|---|---|---|---|---|
| baseline | 512 | 64 | 5 | No | Config minima |
| with_reranker | 512 | 64 | 5 | Sì | Effetto reranker |
| small_chunks | 256 | 32 | 5 | Sì | Chunk piccoli |
| large_chunks | 1024 | 128 | 5 | Sì | Chunk grandi |
| high_recall | 512 | 64 | 10 | Sì | Maggiore recall |
| strict_threshold | 512 | 64 | 10 | Sì | Score threshold 0.3 |

**10 query di test** in italiano su categorie: organi, normativa, formazione, commissioni, contatti, albo, servizi.

**Output:** tabella colorata + file JSON `benchmarks/results.json`.

---

## 13. Notebooks

### `notebooks/01_analisi_esplorativa_dati_cni.ipynb`

Analisi esplorativa dei dati crawlti dal CNI.

**Sezioni:**
1. Caricamento documenti
2. Distribuzione per categoria (bar chart)
3. Distribuzione lunghezza contenuti (istogramma + boxplot)
4. Quality check: repetition ratio per documento
5. Statistiche chunking
6. Top 15 sezioni del sito coperte dal crawl
7. Riepilogo statistiche

**Dipendenze:** pandas, matplotlib, seaborn

### `notebooks/02_demo_tesi_relatore.ipynb`

Notebook dimostrativo per il relatore di tesi.

**Sezioni:**
1. Panoramica dell'architettura
2. Componenti del sistema
3. Flusso RAG con LangGraph
4. Query esempio (con retrieval)
5. Confronto con/senza reranker
6. Metriche di valutazione spiegate
7. Come eseguire il progetto completo

---

## 14. Test

### `tests/unit/test_chunker.py`

Test per `DocumentChunker`:
- Test chunking di testi lunghi (multi-chunk)
- Test testi brevi (single chunk)
- Test contenuti vuoti
- Test preservazione metadati
- Test chunk_index e total_chunks

### `tests/unit/test_retriever.py`

Test per `QueryClassifier`:
- Classificazione normativa
- Classificazione organi
- Classificazione formazione
- Classificazione generico
- Classificazione contatti
- Case insensitivity

### `tests/integration/test_ingestion_pipeline.py`

Test integrazione ingestion:
- `TextCleaner`: rimozione boilerplate
- `TextCleaner`: normalizzazione spazi
- `PublicDataFilter`: URL pubblico vs privato
- `PublicDataFilter`: keyword negate
- `QualityChecker`: contenuto vuoto/troppo corto/valido

### `tests/integration/test_rag_pipeline.py`

Test integrazione RAG:
- `PIIFilter`: filtraggio email, telefono
- `PIIFilter`: disabilitato
- `PromptBuilder`: formato e contenuto
- `CitationBuilder`: struttura e limiti

---

## 15. Configurazione

### `.env.example`

Variabili d'ambiente:
```
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LLM_MODEL=llama-3.2-3b-instruct
EMBEDDING_MODEL=all-MiniLM-L6-v2
QDRANT_MODE=local
QDRANT_PATH=./data/qdrant_db
API_PORT=8000
API_CORS_ORIGINS=http://localhost:4200
```

### `config/rag_config.yaml`

Configurazione principale della pipeline RAG.

**Sezioni:**
- `embedding` — modello, device, batch
- `llm` — provider, base_url, temperatura
- `chunking` — chunk_size, overlap, separators
- `retrieval` — top_k, score_threshold, hybrid_search
- `reranking` — enabled, top_k, model
- `vector_store` — collection_name, distance
- `crawler` — base_url, max_depth, delay, paths
- `quality` — min/max length, repetition ratio

### `config/model_config.yaml`

Specifiche dei modelli.

### `config/qdrant_config.yaml`

Configurazione Qdrant: modalità locale/remoto, path, vettori.

### `config/logging_config.yaml`

Configurazione logging con formati e handler.

---

## 16. Docker

### `Dockerfile`

- Base: `python:3.11-slim`
- Installa build-essential
- Copia requirements.txt e installa dipendenze
- Copia il codice
- Espone porta 8000
- CMD: uvicorn

### `docker-compose.yml`

**Servizi:**

1. **api** — build dallo stesso Dockerfile
   - Porta 8000
   - Volume: data/, config/, logs/
   - Dipende da: .env

2. **qdrant** — immagine ufficiale qdrant/qdrant
   - Porte: 6333 (gRPC), 6334 (HTTP)
   - Volume: qdrant_data

---

## 17. Flusso di Esecuzione

### Setup Iniziale

```bash
# 1. Avvia LM Studio con modello Llama
# 2. Crea virtual env
python -m venv .venv
.venv\Scripts\activate  # Windows

# 3. Installa dipendenze
pip install -r requirements.txt

# 4. Configura .env
cp .env.example .env
```

### Pipeline Completa

```bash
# 5. Crawl e indicizzazione (automatico)
python scripts/run_ingestion.py
# - Scrappa www.cni.it
# - Filtra, pulisce, chunk, embed, indicizza

# 6. Avvia API
python scripts/run_api.py
# - FastAPI su http://localhost:8000

# 7. Frontend
cd frontend
npm install
ng serve
# - Angular su http://localhost:4200

# 8. Benchmark (opzionale)
python benchmarks/run_benchmark.py
# - Testa 6 configurazioni
# - Metriche MRR, Recall@k
```

### Esempio Query API

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Quali sono gli organi del CNI?"}'
```

### Verifica Salute

```bash
curl http://localhost:8000/api/v1/health
```

---

## Riepilogo File Generati

| Modulo | Files | Linee di codice |
|---|---|---|
| Config | 5 | ~180 |
| Core | 3 | ~100 |
| Governance | 4 | ~140 |
| Ingestion | 6 | ~280 |
| Vector Store | 3 | ~150 |
| RAG | 5 | ~280 |
| Inference | 3 | ~100 |
| API | 3 | ~150 |
| Scripts | 4 | ~200 |
| Frontend | 11 | ~350 |
| Tests | 4 | ~200 |
| Benchmark | 1 | ~250 |
| Notebooks | 2 | ~200 (celle) |
| Docker | 2 | ~40 |
| **Totale** | **~56** | **~2.500+** |
