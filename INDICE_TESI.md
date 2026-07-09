# Indice Tesi — Architettura RAG per il Consiglio Nazionale degli Ingegneri

**Autore:** Pietro Poerio
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`
**Branch di riferimento:** `feature/setup-mac`

---

### Capitolo 1 — Fondamenti teorici
1.1 Information Retrieval — modelli classici (TF-IDF, BM25)
1.2 Rappresentazioni neurali del linguaggio — word embeddings, Transformer, sentence-transformers
1.3 Modelli di embedding multilingua — da all-MiniLM-L6-v2 a paraphrase-multilingual-MiniLM-L12-v2
1.4 Large Language Models — architettura, pre-training, fine-tuning, limiti, Qwen 2.5 3B
1.5 Retrieval-Augmented Generation — nascita, architettura, pattern naive → advanced → modular
1.6 Corrective RAG e Self-RAG — grade documents, query rewriting, autovalutazione
1.7 Limiti hardware e transizione piattaforma — da PC Windows (i7-1355U, 16GB, Intel UHD) a MacBook Pro (i5 dual-core 3.1GHz, 8GB, Iris Plus 650)

### Capitolo 2 — Stack tecnologico e strumenti
2.1 Panoramica dell'ecosistema scelto
2.2 LangChain e LangGraph — orchestrazione di pipeline LLM con grafi di stato
2.3 Qdrant — database vettoriale locale (SQLite, HNSW)
2.4 Sentence-Transformers — embedding multilingua con paraphrase-multilingual-MiniLM-L12-v2
2.5 Ollama — esecuzione locale di LLM (Qwen 2.5 3B, Metal GPU)
2.6 FastAPI — backend asincrono con SSE streaming
2.7 Angular 18 — frontend moderno
2.8 httpx + BeautifulSoup + trafilatura — web scraping

### Capitolo 3 — Architettura del sistema RAG
3.1 Requisiti e vincoli di progetto (privacy, nessun cloud, locale, vincoli HW)
3.2 Architettura generale — diagramma a blocchi
3.3 Modulo *Ingestion*: crawler → filtro dati pubblici → quality check → cleaner → chunker → embedder → indexer
3.4 Modulo *RAG (LangGraph)*: classify → retrieve (ibrido) → rerank (cross-encoder) → grade_docs → rewrite_query → build_prompt → generate → self_check → build_citations
3.5 Modulo *Governance*: PII filter, monitoring, qualità contenuti
3.6 Modulo *API*: REST + SSE streaming
3.7 Modulo *Frontend*: chat + statistiche + Qdrant browser
3.8 Flusso dati end-to-end

### Capitolo 4 — Sviluppo del sistema
4.1 Configurazione centralizzata (YAML + env)
4.2 Crawling del sito cni.it (httpx + BeautifulSoup + trafilatura, 5890 documenti)
4.3 Filtraggio, pulizia e quality check
4.4 Chunking (1500 caratteri, overlap 200) e embedding multilingua (384-dim)
4.5 Indicizzazione su Qdrant (17098 chunk, HNSW, cosine distance)
4.6 Pipeline RAG con LangGraph — 9 nodi, 3 archi condizionali
4.7 Retrieval ibrido (categoria + similarità coseno) e reranking (cross-encoder)
4.8 API REST e SSE streaming
4.9 Frontend Angular — chat, statistiche dashboard, Qdrant browser
4.10 Integrazione con Ollama e gestione errori

### Capitolo 5 — Risultati e valutazione
5.1 Metriche di retrieval (MRR, Recall@k, Precision@k)
5.2 Benchmark su 6 configurazioni (baseline, reranker, chunk size, top-k)
5.3 Qualità delle risposte generate (Corrective RAG + Self-RAG)
5.4 Performance: tempi di risposta, uso risorse
5.5 Limiti emersi e osservazioni

### Capitolo 6 — Sviluppi futuri
6.1 Hybrid search con BM25 + vettoriale (sparse + dense)
6.2 Supporto avanzato per PDF (delibere, circolari)
6.3 Query multi-hop e domande complesse
6.4 Feedback utente per miglioramento continuo
6.5 Ottimizzazione su GPU e quantizzazione (modelli >3B)

### Conclusioni

### Appendici
A — Guida all'installazione e configurazione (macOS)
B — Esempi di query e risposte con citazioni
C — Schema della collezione Qdrant

### Bibliografia
