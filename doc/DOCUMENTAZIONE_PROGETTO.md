# Documentazione del Progetto RAG per il CNI

**Titolo:** Architettura RAG per l'estrazione e la consultazione intelligente dei dati pubblici del Consiglio Nazionale degli Ingegneri  
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`  
**Documentazione riferita al branch:** `feature/setup-mac` (macOS)  
**Piattaforma target:** macOS (Ollama + Qdrant locale) — branch `feature/setup-windows` per configurazione Windows

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
┌─────────────────────────────────────────────────────────────────────────┐
│                         CNI RAG System                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  FASE 1: INGESTION (5890 documenti → 17098 chunk)                        │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │Crawler  │→│Downloader│→│Parser    │→│Cleaner   │→│Chunker    │  │
│  │(httpx)  │  │(JSON)    │  │(trafila) │  │(regex)   │  │(1500/200) │  │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘  └─────┬─────┘  │
│                                                                 │        │
│  FASE 2: VECTORIZATION                                           │        │
│                                            ┌────────────────┐   │        │
│                                     ←──────│   Embedder     │←──┘        │
│                                     │      │(multilingual   │            │
│                                     │      │ MiniLM L12-v2) │            │
│                                     │      └───────┬────────┘            │
│                                     │              │                     │
│  FASE 3: INDEXING                     │              │                     │
│                                     │      ┌────────▼────────┐           │
│                                     └──────│    Indexer      │           │
│                                            │  (Qdrant 384d)  │           │
│                                            └─────────────────┘           │
│                                                                          │
│  FASE 4: QUERY (Corrective RAG + Self-RAG via LangGraph)                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐│
│  │Classifier│→│Retriever │→│Reranker  │→│Grade Docs│  │Query     ││
│  │(keyword) │  │(hybrid)  │  │(cross-   │  │(Qwen)    │  │Rewriter  ││
│  └──────────┘  └──────────┘  └──────────┘  └─────┬─────┘  └─────┬─────┘│
│                                                  │              │      │
│                                            pertinente ←──── retry      │
│                                                  │                     │
│                                          ┌───────▼───────┐            │
│                                          │ Prompt Builder │            │
│                                          └───────┬───────┘            │
│                                                  │                     │
│                                          ┌───────▼───────┐            │
│                                          │   Generate    │            │
│                                          │ (Qwen 3B)    │            │
│                                          └───────┬───────┘            │
│                                                  │                     │
│                                          ┌───────▼───────┐            │
│                                          │  Self-Check   │──→Fix     │
│                                          │   (Qwen)      │           │
│                                          └───────┬───────┘            │
│                                                  │                     │
│                                          ┌───────▼───────┐            │
│                                          │   Citations   │            │
│                                          └───────────────┘            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Tecnologie Utilizzate

| Componente | Tecnologia | Ruolo |
|---|---|---|
| Backend | Python 3.12 + FastAPI | API server |
| Frontend | Angular 18 | Interfaccia utente |
| LLM | Qwen 2.5 3B via Ollama (`localhost:11434`) | Generazione risposte, grade docs, query rewrite, self-check |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) | Vettorizzazione testo (50+ lingue) |
| Vector Store | Qdrant (modalità locale SQLite, `data/qdrant_db`) | Database vettoriale |
| Orchestratore | LangGraph (Corrective RAG + Self-RAG) | Pipeline RAG con 9 nodi |
| Framework RAG | LangChain | Chunking, prompt |
| Documenti | httpx + BeautifulSoup + trafilatura | Crawling e parsing |

**Hardware:** 8 GB RAM, CPU Intel/Apple Silicon, GPU non richiesta, Docker non richiesto.

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
│           ├── app.routes.ts
│           ├── components/
│           │   ├── chat/
│           │   │   └── chat.component.ts
│           │   └── statistiche/
│           │       └── statistiche.component.ts
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
│   │   ├── llm_client.py        # Client LLM (Ollama/compatibile OpenAI)
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
│   │   ├── grade_docs.py        # Valutazione pertinenza documenti (Corrective RAG)
│   │   ├── hybrid_retriever.py  # Retrieval ibrido
│   │   ├── prompt_builder.py    # Costruzione prompt
│   │   ├── query_classifier.py  # Classificazione query
│   │   ├── query_rewriter.py    # Riscrittura query (Corrective RAG)
│   │   ├── rag_chain.py         # Orchestrazione LangGraph (9 nodi)
│   │   ├── reranker.py          # Riordinamento risultati
│   │   └── self_rag.py          # Autovalutazione risposta (Self-RAG)
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
  - `create_embeddings()` → HuggingFaceEmbeddings (legge `EMBEDDING_MODEL` da `.env` o `rag_config.yaml`)
   - `create_llm()` → LLM via ChatOpenAI (su Ollama/LM Studio) o LlamaCpp

**Provider supportati:**
- `lm_studio` → ChatOpenAI su endpoint configurato (default Ollama `http://localhost:11434/v1`)
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
- Repetition ratio (default: max 0.65)
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
- `max_depth`: 5 livelli
- `max_pages`: 5000 pagine
- `delay`: 0.3 secondi tra richieste
- `max_links_per_page`: 150
- `allowed_domains`: www.cni.it, cni.it

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
- `chunk_size`: 1500 caratteri
- `chunk_overlap`: 200 caratteri
- `separators`: ["\n\n", "\n", ".", " ", ""]

**Output chunk:** `{content, metadata: {source, title, chunk_index, total_chunks}}`

### `src/ingestion/embedder.py` — `EmbeddingGenerator`

Genera embeddings vettoriali usando `sentence-transformers`.

**Modello:** `paraphrase-multilingual-MiniLM-L12-v2` (12 layer, 384 dimensioni, 50+ lingue supportate). Sostituisce il precedente `all-MiniLM-L6-v2` per migliore comprensione dell'italiano, mantenendo la stessa dimensione 384.

**Metodi:**
- `generate(text)` → embedding singolo
- `generate_batch(texts)` → batch embedding
- `process_chunks(chunks)` → aggiunge campo `embedding` a ogni chunk

---

## 6. Modulo Vector Store

### `src/vectorstore/qdrant_client.py` — `QdrantClientManager`

Gestisce connessione a Qdrant (locale o remoto).

**Modalità:**
- `local` → salva su `./data/qdrant_db` (file-based SQLite, **modalità attiva**)
- `docker` → connessione a `localhost:6333` (container Qdrant, solo branch Windows)

**All'avvio:**
1. Crea directory se locale
2. Connette a Qdrant
3. Crea collezione se non esiste
4. Configura: Cosine distance, dimensione 384, HNSW index

**Stato attuale:** 17098 chunk indicizzati (5890 documenti crawlti), singola collezione `cni_documents`.

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
- `top_k`: 20
- `score_threshold`: 0.3

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

Riordina i risultati retrieved usando un cross-encoder per migliorare la pertinenza dei top-k documenti inviati al LLM.

**Configurazione:**
- `enabled`: true (abilitato per selezionare i documenti più pertinenti)
- `top_k`: 5 (documenti finali dopo reranking)
- `model`: cross-encoder/ms-marco-MiniLM-L-6-v2

**Processo:**
1. Prende i `top_k=10` documenti dal retrieval vettoriale
2. Il cross-encoder valuta ogni coppia (query, documento) e produce uno score di pertinenza
3. Ordina per score decrescente e mantiene i `top_k=5`
4. I 5 documenti finali vanno al grade_docs e al prompt builder

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

Orchestrazione completa del flusso RAG con LangGraph e Corrective RAG + Self-RAG.

**Grafo LangGraph (9 nodi, 4 archi condizionali):**

```
classify ──► retrieve ──► rerank ──► grade_docs ──► build_prompt ──► generate ──► self_check ──► build_citations ──► END
                 │                      │                │                         │                    │
                 │                 non pertinente        │                    inaccurata               │
                 │                      │                │                         │                    │
                 │                rewrite_query          │                     generate(fix)           │
                 │                      │                │                         │                    │
                 │                   retry ──► retrieve  │                         │                    │
                 │                      │                │                         │                    │
                 │                 fallback ──► END      │                         │                    │
                 │                                       │                         │                    │
                 └───────────────────────────────────────┴─────────────────────────┴────────────────────┘
```

**Nodi:**
1. **classify** → QueryClassifier.classify(query) + log monitoring
2. **retrieve** → HybridRetriever.retrieve(query)
3. **rerank** → Reranker.rerank(query, docs) — cross-encoder
4. **grade_docs** → GradeDocs.grade(question, docs) — Qwen valuta se docs sono pertinenti
5. **rewrite_query** → QueryRewriter.rewrite(question) — riscrive query per retry
6. **build_prompt** → PromptBuilder.build_prompt(question, docs)
7. **generate** → PIIFilter → ResponseGenerator.generate(prompt); se fix_attempted, aggiunge istruzione di correzione
8. **self_check** → SelfRAG.check(question, response, docs) — Qwen valuta accuratezza risposta
9. **build_citations** → CitationBuilder.build(docs, response)
10. **fallback** → restituisce messaggio di fallback

**Archi condizionali:**
- `grade_docs` → se `pertinente` → `build_prompt`; se `non pertinente` → `rewrite_query`
- `rewrite_query` → se `retry_count <= 1` → `retrieve` (retry); altrimenti → `fallback`
- `self_check` → se `accurata` → `build_citations`; se `inaccurata` + `!fix_attempted` → `generate` (con fix prompt)

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
    "fallback_triggered": bool,
    "grade_result": str,          # "pertinente" | "non pertinente"
    "retry_count": int,           # 0, 1, 2 (max 1 rewrite)
    "self_check_result": str,     # "accurata" | "inaccurata"
    "fix_attempted": bool,        # True dopo 1 fix
}
```

**Metodi pubblici:**
- `query(question)` → esecuzione sincrona del grafo
- `astream(question)` → generator asincrono per streaming SSE (esecuzione manuale, non LangGraph, per controllo streaming)

### `src/rag/grade_docs.py` — `GradeDocs`

Valuta se i documenti retrieved sono pertinenti alla domanda usando Qwen 2.5 3B.

**Metodo:** `grade(question, docs)` → `"pertinente"` | `"non pertinente"`

**Prompt:**
```
Sei un valutatore di rilevanza. Data una domanda e un insieme di documenti, determina se i documenti contengono informazioni sufficienti per rispondere...
```
Risposta attesa: una sola parola tra `pertinente` e `non pertinente`.

### `src/rag/query_rewriter.py` — `QueryRewriter`

Riscrive la query utente per migliorare il retrieval quando grade_docs fallisce.

**Metodo:** `rewrite(question)` → stringa riscritta

**Prompt:**
```
Riscrivi la seguente domanda in modo più specifico e dettagliato per migliorare la ricerca nei documenti. Mantieni il significato originale...
```

### `src/rag/self_rag.py` — `SelfRAG`

Valuta l'accuratezza della risposta generata, confrontandola con i documenti.

**Metodo:** `check(question, response, docs)` → `"accurata"` | `"inaccurata"`

**Prompt:**
```
Confronta la risposta con i documenti. Identifica eventuali affermazioni non supportate, inesattezze o allucinazioni.
```
Se inaccurata, rigenera con un'istruzione di correzione aggiuntiva (1 solo tentativo).

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
- `IngestResponse`: `{status, documents_crawled, documents_total, chunks_indexed, message}`
- `ErrorResponse`: `{detail, code}`

### `src/api/routes.py` — FastAPI Router

**Endpoint:**

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/v1/query` | Query RAG standard |
| POST | `/api/v1/query/stream` | Query in streaming SSE |
| GET | `/api/v1/health` | Stato del sistema |
| POST | `/api/v1/ingest` | Crawl e indicizzazione |
| GET | `/api/v1/qdrant/stats` | Statistiche collezione Qdrant |
| GET | `/api/v1/qdrant/analytics` | Analytics avanzati (categorie, lunghezza media, top fonti) |
| GET | `/api/v1/qdrant/documents` | Documenti indicizzati (paginazione + ricerca) |
| GET | `/api/v1/qdrant/documents/{id}` | Dettaglio documento |
| GET | `/qdrant` | Pagina HTML Qdrant Browser |

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
- `--max-pages` (default: None — usa valore da `rag_config.yaml`: 5000)
- `--max-depth` (default: None — usa valore da `rag_config.yaml`: 5)
- `--output` (default: data/raw)
- `--delay` (default: None — usa valore da `rag_config.yaml`: 0.3)

### `scripts/run_ingestion.py`

Pipeline completa di ingestion.

**Opzioni CLI:**
- `--crawl/--no-crawl` (default: crawl)
- `--max-pages` (default: 1000)
- `--clear/--no-clear` (default: no-clear) — cancella l'indice prima di re-indicizzare
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

### `frontend/src/app/components/statistiche/statistiche.component.ts`

Pagina Statistiche (`/statistiche`) con analisi visuale dei documenti indicizzati.

**Dati mostrati:**
- Riepilogo: documenti totali, lunghezza media, lunghezza mediana, numero categorie
- Grafico a barre: documenti per categoria
- Grafico a barre: distribuzione lunghezza contenuti (bucket 0-500, 500-1000, ecc.)
- Grafico a barre: top 10 fonti per numero di documenti

**API chiamate:** `getQdrantAnalytics()` → `GET /api/v1/qdrant/analytics`

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
- `queryStream(request)` → POST `/api/v1/query/stream` (SSE via XHR)
- `health()` → GET `/api/v1/health`
- `ingest()` → POST `/api/v1/ingest`
- `getQdrantStats()` → GET `/api/v1/qdrant/stats`
- `getQdrantAnalytics()` → GET `/api/v1/qdrant/analytics`
- `getQdrantDocuments(offset, limit, search?)` → GET `/api/v1/qdrant/documents`

**Streaming:** Implementa EventSource polyfill con XHR per lo streaming SSE.

### `frontend/src/app/models/rag.models.ts`

Interfacce TypeScript:
- `Citation`, `QueryResponse`, `QueryRequest`
- `HealthResponse`, `IngestResponse`
- `ChatMessage`, `StreamEvent`
- `QdrantStatsResponse` — collezione, modalità, punti, vettori
- `QdrantDocument` — id, score, titolo, fonte, categoria, contenuto
- `QdrantDocumentsResponse` — documenti, offset, totale, ricerca
- `QdrantAnalyticsResponse` — documenti totali, lunghezza media/mediana, categorie, bucket lunghezze, top fonti

### `frontend/src/app/app.component.ts`

Componente root con header, navigazione (Chat, Statistiche) e menu impostazioni.

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

Variabili d'ambiente (setup macOS):
```
# Ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:3b

# Embedding
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# Qdrant locale (SQLite, senza Docker)
QDRANT_MODE=local
QDRANT_PATH=./data/qdrant_db

# API
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

## 16. Docker (solo branch Windows)

> Su macOS Docker **non è richiesto**. Questa sezione è mantenuta per il branch `feature/setup-windows`.

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

## 17. Flusso di Esecuzione (macOS)

### Setup Iniziale

```bash
# 1. Avvia Ollama (se non già in esecuzione)
ollama serve

# 2. Scarica il modello LLM
ollama pull qwen2.5:3b

# 3. Crea virtual env
python -m venv .venv
source .venv/bin/activate

# 4. Installa dipendenze
pip install -r requirements.txt

# 5. Configura .env
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

---

## Changelog Fix Applicati

### 2024-06-12 — Fix post-generazione

| # | Bug | File | Gravità |
|---|---|---|---|
| 1 | EventSourcePolyfill non emetteva eventi (XHR senza listener) | `frontend/src/app/services/rag.service.ts` | **CRITICAL** |
| 2 | `safe_prompt` calcolato ma inutilizzato in `_generate` | `src/rag/rag_chain.py:85-87` | **HIGH** |
| 3 | Nessun PII filtering nel path streaming `astream` | `src/rag/rag_chain.py:118-147` | **HIGH** |
| 4 | `response` letta fuori dal `async with` context del client HTTP | `src/ingestion/crawler.py:48-67` | MEDIUM |
| 5 | `sync for` in `async def` bloccava event loop in `astream_generate` | `src/inference/response_generator.py:23` | MEDIUM |
| 6 | `str(event)` produceva Python repr non JSON-valido nello SSE | `src/api/routes.py:64` | MEDIUM |
| 7 | Chat component aspettava risposta completa prima di mostrare messaggio | `frontend/src/app/components/chat/chat.component.ts` | LOW |

**Fix applicati:**
1. Sostituito EventSourcePolyfill con XHR `onprogress` che legge incrementalmente `responseText` e fa `JSON.parse` sulle linee `data:`
2. `_generate` ora filtra ogni messaggio del prompt con `pii_filter.filter()` prima di inviarlo al LLM
3. `astream` ora applica `pii_filter.filter()` su domanda e su ogni chunk della risposta
4. L'intero blocco di elaborazione della response (`content_type`, `_process_html`, link extraction) ora è indentato dentro `async with`
5. `astream_generate` usa `loop.run_in_executor(None, next, sync_gen)` per non bloccare l'event loop
6. Streaming SSE ora usa `json.dumps(event)` invece di `str(event)`
7. Il messaggio dell'assistant viene creato subito (vuoto) e popolato quando arriva la risposta

---

## Riepilogo File Generati

| Modulo | Files | Linee di codice |
|---|---|---|
| Config | 5 | ~180 |
| Core | 3 | ~100 |
| Governance | 4 | ~140 |
| Ingestion | 6 | ~280 |
| Vector Store | 3 | ~150 |
| RAG | 8 | ~450 |
| Inference | 3 | ~100 |
| API | 3 | ~150 |
| Scripts | 4 | ~200 |
| Frontend | 11 | ~350 |
| Tests | 4 | ~200 |
| Benchmark | 1 | ~250 |
| Notebooks | 2 | ~200 (celle) |
| Docker | 2 | ~40 |
| **Totale** | **~59** | **~2.800+** |
