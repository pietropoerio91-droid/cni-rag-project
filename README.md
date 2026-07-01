# CNI RAG — Architettura RAG per il Consiglio Nazionale degli Ingegneri

Sistema RAG (Retrieval-Augmented Generation) per l'estrazione e la consultazione intelligente dei dati pubblici del [Consiglio Nazionale degli Ingegneri (CNI)](https://www.cni.it/).

## Architettura

```
                   ┌─────────────────────────────────────────────────┐
                   │                  INGESTION                       │
                   │  Crawler → Parser → Cleaner → Chunker → Embedder │
                   └───────────────────────┬─────────────────────────┘
                                           │
                                           ▼
                                   ┌──────────────┐
                                   │     Qdrant    │
                                   │  (locale,     │
                                   │   SQLite)     │
                                   └──────┬───────┘
                                           │
                   ┌───────────────────────┴─────────────────────────┐
                   │                   QUERY                          │
                   │  Retriever → Reranker → Prompt Builder → LLM    │
                   │                                      (qwen2.5:3b│
                   │                                       via Ollama)│
                   └───────────────────────┬─────────────────────────┘
                                           │
                                   ┌───────┴────────┐
                                   │    FastAPI      │
                                   │   (REST/SSE)    │
                                   └───────┬────────┘
                                           │
                                   ┌───────┴────────┐
                                   │  Angular FE    │
                                   │  localhost:4200 │
                                   └────────────────┘
```

## Tecnologie

- **Backend**: Python 3.12 + FastAPI
- **Frontend**: Angular 18
- **LLM**: Qwen 2.5 3B via Ollama (locale, `http://localhost:11434`)
- **Embeddings**: `all-MiniLM-L6-v2` (sentence-transformers, 384-dim)
- **Vector Store**: Qdrant (modalità locale SQLite, `data/qdrant_db`)
- **Orchestrator**: LangGraph
- **Framework RAG**: LangChain

## Hardware Consigliato

| Componente | Minimo |
|------------|--------|
| RAM | 8 GB |
| CPU | Intel o Apple Silicon |
| GPU | Non richiesta (tutto su CPU) |
| OS | macOS (testato) o Windows |
| Docker | Non richiesto |

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
│   └── qdrant_db/           # Database vettoriale (SQLite)
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
├── frontend/                # Applicazione Angular
└── requirements.txt
```

## Prerequisiti

1. **Python 3.12+**
2. **Ollama** con modello scaricato: `ollama pull qwen2.5:3b`
3. **Node.js 20+** e **Angular CLI** (`npm install -g @angular/cli`)
4. Nessun Docker richiesto (Qdrant in modalità locale)

## Setup Rapido

> ⚠️ La prima indicizzazione può richiedere diversi minuti (crawling + embedding). Pazientare.

### Passo per passo

```bash
# 1. Clona il repo
git clone <repo-url>
cd cni-rag-project

# 2. Ambiente virtuale
python -m venv .venv
source .venv/bin/activate

# 3. Installa dipendenze
pip install -r requirements.txt

# 4. Copia .env (modifica se necessario)
cp .env.example .env

# 5. Avvia Ollama (se non già in esecuzione)
ollama serve

# 6. Verifica che il modello sia disponibile
ollama pull qwen2.5:3b

# 7. Ingestion (prima volta)
python scripts/run_ingestion.py --max-pages 100

# 8. Avvia API server
python scripts/run_api.py

# 9. Avvia frontend Angular (in un altro terminale)
cd frontend
npm install
./node_modules/.bin/ng serve
```

### Unico comando (macOS / Linux)

```bash
chmod +x run.sh && ./run.sh
```

## Avvio Rapido su Mac (dopo il primo setup)

Comandi giornalieri per riavviare i servizi dopo un riavvio del sistema:

```bash
# 1. Assicurati che Ollama sia in esecuzione
ollama serve

# 2. Avvia API server in screen
screen -dmS api bash -c "cd /Users/pietropoerio/Desktop/cni-rag-project && python3 scripts/run_api.py --no-reload --port 8000 > /tmp/api_uvicorn.log 2>&1"

# 3. Avvia frontend Angular (in un altro terminale)
/tmp/node-v20.12.0-darwin-x64/bin/node /tmp/node-v20.12.0-darwin-x64/bin/npm run start --prefix /Users/pietropoerio/Desktop/cni-rag-project/frontend

# 4. Verifica
curl http://localhost:8000/api/v1/health && echo ""
```

> Nota: Node.js è installato in `/tmp/node-v20.12.0-darwin-x64/bin/`. Se il frontend non si avvia, verifica il percorso con `ls /tmp/node-v20.12.0-darwin-x64/bin/node`.

Se vuoi rientrare nella sessione screen dell'API:
```bash
screen -r api
# Per staccarti senza fermare: Ctrl+A, D
```

Per fermare i servizi:
```bash
kill $(lsof -t -i :8000) 2>/dev/null   # ferma API
kill $(lsof -t -i :4200) 2>/dev/null   # ferma frontend
```

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/v1/query` | POST | Query RAG (domanda → risposta + citazioni) |
| `/api/v1/query/stream` | POST | Query in streaming SSE |
| `/api/v1/ingest` | POST | Crawl e indicizzazione |
| `/api/v1/health` | GET | Stato del sistema |
| `/api/v1/qdrant/stats` | GET | Statistiche collezione Qdrant |
| `/api/v1/qdrant/analytics` | GET | Analytics avanzati |
| `/api/v1/qdrant/documents` | GET | Documenti indicizzati |
| `/api/v1/qdrant/documents/{id}` | GET | Dettaglio documento |
| `/qdrant` | GET | Esplora documenti (HTML) |

### Esempio Query

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Quali sono gli organi del CNI?"}'
```

## Branch

| Branch | Descrizione |
|--------|-------------|
| `main` | Base comune |
| `feature/setup-mac` | Configurazione macOS (Ollama + Qdrant locale) |
| `feature/setup-windows` | Configurazione Windows (Docker + LM Studio, se usato) |

## Licenza

Progetto a scopo di ricerca e dimostrativo.
