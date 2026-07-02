## Goal
- Sistema RAG per il Consiglio Nazionale degli Ingegneri (CNI): crawler sito → chunking → embedding → Qdrant → retrieval + LLM Ollama → frontend Angular

## Constraints & Preferences
- Ollama su `localhost:11434` con `qwen2.5:3b`
- Qdrant locale SQLite (`data/qdrant_db`), Docker non disponibile
- Solo CPU Intel i5, 8 GB RAM
- Frontend Angular standalone su `localhost:4200`, Node v20.12.0 in `/tmp`

## Progress
### Done
- **Embedding model cambiato**: `all-MiniLM-L6-v2` (384-dim, inglese) → `paraphrase-multilingual-MiniLM-L12-v2` (768-dim, 50+ lingue)
- **Qdrant vector size**: 384 → 768
- **`/servizi` aggiunto** a `included_paths` e `priority_paths`
- **`/en/` bloccato** in `DENIED_PATTERNS` del crawler (1.594 file inglese esclusi)
- **Reranker abilitato**: `top_k=10` retrieval → cross-encoder → `top_k=5` al LLM
- **Fix fork lock Qdrant**: `indexer.close()` prima degli embedding
- **Re-index completato** (17.100 chunk con vecchio modello, da rifare col nuovo)
- **Fallback su score basso**: se max score < 0.5, salta LLM
- **Endpoint ingest status**: `GET /api/v1/ingest/status`
- **Frontend**: progress bar, suggestions aggiornate

## Key Decisions
- `paraphrase-multilingual-MiniLM-L12-v2` per retrieval in italiano (768-dim, 12 layers)
- `included_paths`: `/media-ing`, `/cni`, `/temi`, `/contatti`, `/servizi`
- `/en/` escluso dal crawl (27% dei dati era inglese, non serve per utenti italiani)
- `--clear` pericoloso: cancella indice all'inizio — fix in sospeso

## Stato Attuale
- Qdrant VUOTO (vector size cambiato, serve re-index completo)
- Dati raw su disco: 5.888 JSON dal vecchio crawl (include `/en/`, va filtrato)
- API ferma (andrà riavviata dopo re-index)

## Next Steps
- Ricreare collezione Qdrant con 768 dim
- Rilanciare crawl + ingestion con nuovo modello embedding
- Riavviare API
- Testare retrieval su domande in italiano

## Config Attuale
- `embedding.model_name: paraphrase-multilingual-MiniLM-L12-v2`
- `qdrant.vectors.size: 768`
- `retrieval.top_k: 10`, `score_threshold: 0.3`
- `reranking.enabled: true`, `reranking.top_k: 5`
- `fallback.score_threshold: 0.5`
- `crawler.included_paths: [/media-ing, /cni, /temi, /contatti, /servizi]`
- `crawler.priority_max_depth: 12`, `max_pages: 15000`
- `chunking.chunk_size: 1500`, `chunk_overlap: 200`

## Relevant Files
- `config/rag_config.yaml`: embedding model, paths, retrieval, reranker, fallback
- `config/qdrant_config.yaml`: vector size 768, local SQLite
- `config/model_config.yaml`: model reference
- `src/ingestion/crawler.py`: DENIED_PATTERNS include /en/
- `src/vectorstore/qdrant_client.py`: QdrantClientManager singleton
- `src/vectorstore/indexer.py`: clear_index, close(), index_chunks
- `scripts/run_ingestion.py`: pipeline, close() prima di embedding
- `scripts/run_api.py`: API server
