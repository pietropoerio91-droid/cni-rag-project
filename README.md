# CNI RAG - Architettura RAG per il Consiglio Nazionale degli Ingegneri

Sistema RAG (Retrieval-Augmented Generation) per l'estrazione e la consultazione intelligente dei dati pubblici del [Consiglio Nazionale degli Ingegneri (CNI)](https://www.cni.it/).

## Architettura

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│  Crawler    │───>│   Cleaner    │───>│   Chunker    │───>│  Embedder        │
│  (httpx+BS) │    │  (trafilatura)│   │  (langchain) │    │  (multilingual)  │
│             │    │              │    │  (1500 char)  │    │  (384-dim)       │
└─────────────┘    └──────────────┘    └──────────────┘    └────────┬─────────┘
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
- **LLM**: via LM Studio (locale) — es. Llama 3.2 3B, Mistral 7B, Qwen 2.5 7B
- **Embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, 384-dim, multilingua)
- **Vector Store**: Qdrant (Docker, container su `localhost:6333`)
- **Qdrant UI**: http://localhost:6333/dashboard
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
2. **Docker** (per Qdrant) — avvia con `docker compose up -d qdrant`
3. **LM Studio** con un modello LLM in esecuzione su `http://localhost:1234`
   - In LM Studio, abilita **CORS** nelle impostazioni (sezione "Serve" → "Enable CORS")
4. **Node.js 20+** e **Angular CLI** (`npm install -g @angular/cli`)

## Setup Rapido

> ⚠️ La prima indicizzazione può richiedere diversi minuti (crawling + embedding). Pazientare.

### Unico comando (Windows)

```powershell
.\run.ps1
```

Attiva venv, installa dipendenze, fa ingestion se necessario, avvia API e frontend.

### Con un comando

```powershell
.\run.ps1              # Avvia tutto (API + frontend)
```

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

# 4. Avvia Qdrant (Docker)
docker compose up -d qdrant

# 5. Avvia LM Studio con un modello LLM su http://localhost:1234

# 6. Ingestion (prima volta)
python scripts/run_ingestion.py                     # Crawl + indicizzazione
python scripts/run_ingestion.py --no-crawl --clear  # Re-indicizza senza crawl

# 7. Avvia API server
python scripts/run_api.py

# 8. Avvia frontend Angular
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
| `/api/v1/qdrant/stats` | GET | Statistiche collezione Qdrant |
| `/api/v1/qdrant/documents` | GET | Documenti indicizzati (con paginazione e ricerca) |
| `/qdrant` | GET | Pagina HTML per esplorare i documenti |

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

L'app Angular sarà disponibile su `http://localhost:4200`:
- **Chat** (`/`) — Interfaccia principale per fare domande
- **Statistiche** (`/statistiche`) — Metriche live del database vettoriale (punti, vettori, documenti con ricerca)

## Licenza

Progetto a scopo di ricerca e dimostrativo.
