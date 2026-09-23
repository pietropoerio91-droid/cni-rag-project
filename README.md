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
                    ┌───────────────────────┴──────────────────────────────────────┐
                    │                         QUERY                                 │
                    │  Classifier → Retriever → Reranker → Grade Docs ──→ Rewrite  │
                    │                                           │         │         │
                    │                                     pertinente    retry      │
                    │                                           │         │         │
                    │                                     Prompt Builder ←─┘       │
                    │                                           │                  │
                    │                                        Generate              │
                    │                                           │                  │
                    │                                      Self-Check ──→ Fix     │
                    │                                           │                  │
                    │                                   Build Citations            │
                    │                                      (qwen2.5:3b             │
                    │                                       via Ollama)            │
                    └───────────────────────┬──────────────────────────────────────┘
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
- **Embeddings**: `intfloat/multilingual-e5-small` (sentence-transformers, 384-dim, prefissi `query:`/`passage:` automatici)
- **Vector Store**: Qdrant (modalità locale SQLite, `data/qdrant_db`) — recupero ibrido: vettore denso + vettore sparso BM25 nativo, fusi con Reciprocal Rank Fusion
- **Reranker**: `BAAI/bge-reranker-base` (confrontato con `mmarco-mMiniLMv2-L12-H384-v1` e `bge-reranker-v2-m3`, vedi `doc/TEST_RECUPERO_IBRIDO.md`)
- **Orchestrator**: LangGraph (Corrective RAG + Self-RAG)
- **Framework RAG**: LangChain

## Hardware Consigliato

| Componente | Minimo |
|------------|--------|
| RAM | 8 GB |
| CPU | Intel o Apple Silicon |
| GPU | Non richiesta (tutto su CPU) |
| OS | macOS o Windows (istruzioni per entrambi più sotto) |
| Docker | Non richiesto |

> **Isolamento fra macchine**: `data/` (compresi `data/qdrant_db` e `data/processed`) è nel
> `.gitignore`, quindi un `git clone` su un'altra macchina parte sempre senza indice e senza
> documenti scaricati. Qdrant in modalità locale legge e scrive solo su disco locale
> (`./data/qdrant_db`, relativo alla cartella del progetto): un'indicizzazione lanciata su
> Windows scrive nel *suo* `data/qdrant_db`, fisicamente separato da quello del Mac, e non
> può in alcun modo sovrascriverlo — a meno di clonare il progetto in una cartella
> sincronizzata fra le due macchine (Dropbox, OneDrive, cartella condivisa di una VM): in tal
> caso i due `data/qdrant_db` coinciderebbero e l'indicizzazione su una macchina
> cancellerebbe quella dell'altra. Clonare in due cartelle indipendenti è sufficiente a
> evitare il problema.

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
│   ├── rag/                 # RAG chain, retriever, reranker, grade_docs, query_rewriter, self_rag
│   └── vectorstore/         # Qdrant client, indexer, retriever
├── tests/                   # Test
│   ├── unit/
│   └── integration/
├── .env.example             # Variabili d'ambiente facoltative (la configurazione vera è in config/)
├── archivio/                # File superati, conservati temporaneamente (vedi archivio/README.md)
├── frontend/                # Applicazione Angular
└── requirements.txt
```

## Prerequisiti

1. **Python 3.12+**
2. **Ollama** (non LM Studio — il sistema è configurato per l'API di Ollama) con modello
   scaricato: `ollama pull qwen2.5:3b`
3. **Node.js 20+** e **Angular CLI** (`npm install -g @angular/cli`)
4. Nessun Docker richiesto (Qdrant in modalità locale)

Prerequisiti identici su macOS e Windows: cambia solo la shell dei comandi qui sotto.

## Setup Rapido

> ⚠️ La prima indicizzazione può richiedere diversi minuti (crawling + embedding). Pazientare.

### Passo per passo — macOS / Linux (bash)

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

# 7. Ingestion (prima volta — richiede diversi minuti: crawl + embedding di ~13.000 chunk)
python scripts/run_ingestion.py

# 8. Avvia API server
python scripts/run_api.py --no-reload

# 9. Avvia frontend Angular (in un altro terminale)
cd frontend
npm install
npx ng serve --port 4200
```

Se il sistema non trova Node.js (per esempio su un Mac senza installazione globale), un'alternativa è scaricarlo in una cartella temporanea e aggiungerla al `PATH` solo per quella sessione di terminale — sostituendo `darwin-x64` con l'architettura corretta (`darwin-arm64` su Apple Silicon):
```bash
curl -fsSL https://nodejs.org/dist/v20.12.0/node-v20.12.0-darwin-x64.tar.gz | tar -xz -C /tmp/
export PATH="/tmp/node-v20.12.0-darwin-x64/bin:$PATH"
```

### Passo per passo — Windows (PowerShell)

```powershell
# 1. Clona il repo
git clone <repo-url>
cd cni-rag-project

# 2. Ambiente virtuale
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Installa dipendenze
pip install -r requirements.txt

# 4. Copia .env (modifica se necessario)
Copy-Item .env.example .env

# 5. Avvia Ollama (se non già in esecuzione, in un altro terminale)
ollama serve

# 6. Verifica che il modello sia disponibile
ollama pull qwen2.5:3b

# 7. Ingestion (prima volta — richiede diversi minuti)
python scripts/run_ingestion.py

# 8. Avvia API server
python scripts/run_api.py --no-reload

# 9. Avvia frontend Angular (in un altro terminale)
cd frontend
npm install
npx ng serve --port 4200
```

Node.js va installato normalmente da [nodejs.org](https://nodejs.org/) (nessuna variante
"portatile" come su macOS): l'installer di Windows aggiunge già `node`/`npm` al `PATH`.

### Un comando solo

macOS/Linux:
```bash
# Prima: avvia Ollama in un terminale separato
ollama serve

# Poi, dalla cartella del progetto (dove hai clonato il repo):
chmod +x run.sh && ./run.sh
```

Windows:
```powershell
# Prima: avvia Ollama in un terminale separato
ollama serve

# Poi, dalla cartella del progetto:
.\run.ps1
```

Lo script (`run.sh` o `run.ps1`):
- crea/attiva il virtual environment e installa le dipendenze se mancano
- lancia l'ingestion solo se `data/qdrant_db` è vuota (prima volta)
- avvia API (`--no-reload`) e frontend Angular
- `run.sh` scarica anche Node.js in `/tmp/` automaticamente se manca

## Avvio Rapido (dopo il primo setup — manuale)

macOS/Linux:
```bash
# 1. Ollama (in un terminale)
ollama serve

# 2. API (in un altro terminale, dalla cartella del progetto)
source .venv/bin/activate
python scripts/run_api.py --no-reload

# 3. Frontend (in un altro terminale ancora, dalla cartella del progetto)
cd frontend && npx ng serve --port 4200

# 4. Verifica
curl http://localhost:8000/api/v1/health
```

Per fermare i servizi:
```bash
kill $(lsof -t -i :8000) 2>/dev/null   # ferma API
kill $(lsof -t -i :4200) 2>/dev/null   # ferma frontend
```

Windows:
```powershell
# 1. Ollama (in un terminale)
ollama serve

# 2. API (in un altro terminale, dalla cartella del progetto)
.venv\Scripts\Activate.ps1
python scripts/run_api.py --no-reload

# 3. Frontend (in un altro terminale ancora, dalla cartella del progetto)
cd frontend; npx ng serve --port 4200

# 4. Verifica
curl http://localhost:8000/api/v1/health
```

Per fermare i servizi su Windows, chiudi le rispettive finestre di PowerShell, oppure:
```powershell
Get-Process | Where-Object {$_.Id -in (Get-NetTCPConnection -LocalPort 8000,4200 -ErrorAction SilentlyContinue).OwningProcess} | Stop-Process
```

### Riavvio API prima di script che usano Qdrant direttamente

Qdrant in modalità locale (`data/qdrant_db`) usa un lock a livello di processo: un solo
processo alla volta può accedervi. Se l'API resta attiva, qualsiasi script che apre
direttamente il database (es. `benchmarks/oracle_context.py`, `benchmarks/compare_embeddings.py`,
`benchmarks/ablation_retrieval.py`, `benchmarks/diagnosi_soglia.py`) fallisce con:

```
RuntimeError: Storage folder ./data/qdrant_db is already accessed by another instance of Qdrant client
```

Prima di lanciare uno di questi script (o per un riavvio pulito dell'API), termina il
processo.

macOS/Linux:
```bash
pkill -9 -f run_api.py
```
- `pkill -f` cerca il processo per corrispondenza sull'intera riga di comando (necessario
  perché il processo gira come `python scripts/run_api.py ...`, non come `run_api.py`)
- `-9` invia `SIGKILL`, terminazione immediata e forzata — un kill "gentile" a volte non
  libera il lock di Qdrant abbastanza in fretta

Windows:
```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*run_api.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Dopo aver eseguito lo script, riavvia normalmente l'API (`./scripts/restart_api.sh` su
macOS/Linux, oppure `python scripts/run_api.py --no-reload` su entrambi — non esiste ancora
uno `restart_api.ps1` per Windows).

## Aggiornare l'indice senza perdere quello validato

1. Menu impostazioni (⚙️) → **Indicizza Dati**: crawl completo di cni.it e indicizzazione
   (richiede ore). I dati finiscono in una **collection nuova**
   (`<collection in uso>_ingest_<data_ora>`); quella in uso non viene toccata.
2. A fine indicizzazione la collection nuova compare nella sezione **Collection** dello
   stesso menu, con il numero di chunk.
3. **Usa** la attiva per chat, statistiche e nuove valutazioni. La scelta viene salvata in
   `config/qdrant_config.yaml` e resta dopo un riavvio. Per tornare indietro basta attivare
   di nuovo quella precedente: nessuna collection viene cancellata.

La collection su cui sono stati validati i risultati della tesi è `cni_documents_e5_bm25`.

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/v1/query` | POST | Query RAG (domanda → risposta + citazioni) |
| `/api/v1/query/stream` | POST | Query in streaming SSE |
| `/api/v1/ingest` | POST | Crawl e indicizzazione su una **collection nuova**; quella in uso non viene toccata |
| `/api/v1/ingest/status` | GET | Avanzamento dell'indicizzazione |
| `/api/v1/collections` | GET | Collection presenti, chunk, compatibilità e quale è attiva |
| `/api/v1/collections/active` | PUT | Cambia la collection attiva (salvato in `config/qdrant_config.yaml`) |
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

| Branch / tag | Descrizione |
|--------|-------------|
| `main` | **Versione finale**: recupero ibrido (e5-small + BM25 nativo), reranker `bge-reranker-base`, indicizzazione su collection separata e scelta della collection dal frontend |
| tag `congelato-2026-09-23` | Versione finale congelata per la tesi |
| tag `congelato-2026-09-21-e5` | Configurazione con cui è stato misurato il run `FINAL_V3` |
| tag `sperimentazione-recupero-ibrido` | Implementazione BM25 in memoria usata per la matrice a 6 configurazioni (riproducibilità) |

Gli altri branch (`release/recupero-ibrido`, `feature/*`, `fix/*`, `docs/*`, `exp/*`,
`config/*`, `backup/*`) sono storici: il loro contenuto utile è già su `main`.
macOS e Windows sono entrambi supportati da `main`, con Ollama (non Docker, non LM Studio):
vedi la sezione Setup Rapido qui sopra.

## Licenza

Progetto a scopo di ricerca e dimostrativo.
