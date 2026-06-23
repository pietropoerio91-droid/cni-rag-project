# CNI RAG - Architettura RAG per il Consiglio Nazionale degli Ingegneri

Sistema RAG (Retrieval-Augmented Generation) per l'estrazione e la consultazione intelligente dei dati pubblici del [Consiglio Nazionale degli Ingegneri (CNI)](https://www.cni.it/).

## Architettura

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Crawler    │───>│   Cleaner    │───>│   Chunker    │───>│  Embedder    │
│  (httpx+BS) │    │  (trafilatura)│   │  (langchain) │    │ (MiniLM-L6)  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────┬───────┘
                                                                   │
                                                         ┌─────────▼────────┐
                                                         │  Qdrant Vector   │
                                                         │     Store        │
                                                         └─────────┬────────┘
                                                                   │
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────┴───────┐
│  Angular FE │<───│  FastAPI     │<───│  LangGraph   │<───│  Retriever   │
│  (localhost  │    │  (REST/SSE)  │    │  Orchestrator│    │  (Hybrid)    │
│    :4200)    │    └──────────────┘    └──────┬───────┘    └──────────────┘
└─────────────┘                                 │
                                         ┌──────▼───────┐
                                         │  LLM (Llama) │
                                         │  LM Studio   │
                                         │  localhost    │
                                         │   :1234       │
                                         └──────────────┘
```

## Tecnologie

- **Backend**: Python + FastAPI
- **Frontend**: Angular 18
- **LLM**: Llama 3.2 via LM Studio (locale)
- **Embeddings**: all-MiniLM-L6-v2 (sentence-transformers)
- **Vector Store**: Qdrant (locale SQLite o Docker)
- **Qdrant UI**: http://localhost:6333/dashboard (solo in modalità Docker)
- **Orchestrator**: LangGraph
- **Framework RAG**: LangChain

## Struttura del Progetto

```
cni-rag-project/
├── config/                  # Configurazioni YAML
│   ├── logging_config.yaml
│   ├── model_config.yaml
│   ├── qdrant_config.yaml
│   └── rag_config.yaml
├── data/                    # Dati (gitignorati)
│   ├── raw/                 # Documenti grezzi
│   ├── processed/           # Documenti processati
│   ├── chunks/              # Chunk testuali
│   └── qdrant_db/           # Database vettoriale
├── scripts/                 # Script CLI
│   ├── run_crawler.py       # Crawl del sito CNI
│   ├── run_ingestion.py     # Pipeline di ingestion
│   ├── build_index.py       # Ricostruzione indice
│   └── run_api.py           # Avvio API server
├── src/                     # Codice sorgente Python
│   ├── api/                 # FastAPI endpoints
│   ├── core/                # Config, logging, factory
│   ├── governance/          # Filtri PII, qualità, monitoring
│   ├── inference/           # LLM client, response, citazioni
│   ├── ingestion/           # Crawler, parser, chunker, embedder
│   ├── rag/                 # RAG chain, retriever, reranker
│   └── vectorstore/         # Qdrant client, indexer, retriever
├── tests/                   # Test
│   ├── unit/
│   └── integration/
├── .env.example             # Template variabili ambiente
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Prerequisiti

1. **Python 3.11+**
2. **LM Studio** con modello Llama 3.2 (o compatibile) in esecuzione su `http://localhost:1234`
   - In LM Studio, abilita **CORS** nelle impostazioni (sezione "Serve" → "Enable CORS")
3. **Node.js 20+** e **Angular CLI** (`npm install -g @angular/cli`)
4. **Docker** (opzionale, per Qdrant via Docker invece che locale)

## Setup Rapido

> ⚠️ La prima indicizzazione può richiedere diversi minuti (crawling + embedding). Pazientare.

### Unico comando (Windows)

```powershell
.\run.ps1
```

Attiva venv, installa dipendenze, fa ingestion se necessario, avvia API e frontend.

### Passo per passo

```bash
# 1. Clona il repo
git clone <repo-url>
cd cni-rag-project

# 2. Ambiente virtuale
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Installa dipendenze
pip install -r requirements.txt

# 4. Configura ambiente
cp .env.example .env
# Modifica .env se necessario (default: Qdrant locale, nessun Docker richiesto)

# 5. (Opzionale) Avvia Qdrant via Docker (per UI dashboard)
docker-compose up -d qdrant
# Poi imposta QDRANT_MODE=docker in .env

# 6. Avvia LM Studio con un modello Llama (es. llama-3.2-3b-instruct)
#    su http://localhost:1234

# 7. (Opzionale) Crawling + Ingestion
python scripts/run_ingestion.py              # Crawl + indicizzazione (completo)
python scripts/run_ingestion.py --no-crawl   # Solo indicizzazione (se già crawlsito)
python scripts/run_crawler.py                # Solo crawling

# 8. Avvia API server
python scripts/run_api.py

# 9. Avvia frontend Angular
cd frontend
npm install
ng serve
```

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/v1/query` | POST | Query RAG (domanda → risposta + citazioni) |
| `/api/v1/query/stream` | POST | Query in streaming SSE |
| `/api/v1/ingest` | POST | Crawl e indicizzazione |
| `/api/v1/health` | GET | Stato del sistema |

### Esempio Query

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Quali sono gli organi del CNI?"}'
```

## Frontend Angular

```bash
cd frontend
npm install
ng serve
```

L'app Angular sarà disponibile su `http://localhost:4200`.

## Licenza

Progetto a scopo di ricerca e dimostrativo.
