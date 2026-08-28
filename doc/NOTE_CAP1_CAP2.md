# Note di lavoro — Capitoli 1 e 2

> ⚠️ **Materiale di lavoro, non testo da consegnare.** Fatti verificati e
> riferimenti bibliografici di partenza per scrivere i capitoli 1 e 2 con le
> proprie parole — stessa logica di `CONCLUSIONI_TESI.md`: l'uso di AI
> concordato copre lo sviluppo del progetto, non la redazione della tesi.

---

## Capitolo 2 — Stack tecnologico (fatti verificati dal codice del progetto)

**2.1 Panoramica e criteri di selezione**
Criterio guida: tutto deve girare in locale su 8 GB RAM, CPU dual-core,
nessuna GPU. Ogni scelta tecnologica successiva discende da questo vincolo
(temi da sviluppare: perché non servizi cloud, perché modelli piccoli,
perché niente Docker su questa piattaforma).

**2.2 LangChain e LangGraph**
- LangChain: framework di orchestrazione LLM, usato qui per il chunking
  (`RecursiveCharacterTextSplitter`) e come wrapper verso il LLM
  (`ChatOpenAI` compatibile Ollama)
- LangGraph: libreria per costruire pipeline come grafi di stato con archi
  condizionali — nel progetto: 10 nodi (9 + fallback), 3 punti di decisione
  condizionale (`grade_docs`, `rewrite_query`, `self_check`)
- Concetto chiave da spiegare: differenza fra pipeline lineare e grafo con
  retry/branching — è ciò che rende possibile il Corrective RAG (cap. 1.6)

**2.3 Qdrant**
- Database vettoriale open-source, modalità locale su SQLite (non serve
  Docker), path `data/qdrant_db`
- Indice HNSW (Hierarchical Navigable Small World) — spiegare cos'è:
  struttura a grafo multi-livello per ricerca approssimata del vicino più
  prossimo, sublineare rispetto a scansione esaustiva
- Distanza coseno, dimensione vettori 384
- Nota da citare: la ricerca HNSW è approssimata, non esatta — osservato
  empiricamente (due run identici danno risultati leggermente diversi),
  utile anche per il cap. 5/7

**2.4 Sentence-Transformers**
- Libreria per embedding e cross-encoder
- Embedding: `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, 12 layer,
  50+ lingue
- Reranker: `BAAI/bge-reranker-base`, cross-encoder multilingue (sostituisce
  un modello solo-inglese usato inizialmente — buon aneddoto per il cap.
  5.3 sulle insidie metodologiche)
- Limite tecnico da menzionare qui o in 4.5: il modello di embedding tronca
  a 128 token; i chunk indicizzati hanno mediana 266 token — l'82% viene
  tagliato. Dato reale, da `results/diagnostics_2026-08-27_12-25.json`

**2.5 Ollama**
- Runtime locale per LLM, API compatibile OpenAI su `localhost:11434`
- Modello: `qwen2.5:3b`
- Punto chiave: su Mac Intel, Ollama non usa l'accelerazione Metal
  (disponibile solo su Apple Silicon) → inferenza 100% CPU-bound. È la
  causa tecnica diretta delle latenze misurate (150-300+ secondi per
  domanda)

**2.6 Acquisizione documentale**
- `httpx` (client HTTP asincrono) + `BeautifulSoup` (parsing HTML) +
  `trafilatura` (estrazione testo pulito) + `PyMuPDF`/`fitz` (estrazione
  testo da PDF)
- Crawler: 5 worker concorrenti, coda asincrona (`asyncio.Queue`)

**2.7 Interfacce**
- FastAPI (26 endpoint totali, prefix `/api/v1`), streaming SSE per le
  risposte token-per-token
- Frontend Angular 18, standalone components

Fonte primaria per tutti questi fatti: `doc/SISTEMA.md` (verificato contro
il codice sorgente attuale, non contro documentazione precedente).

---

## Capitolo 1 — Fondamenti e stato dell'arte (struttura + riferimenti verificati)

Solo mappa concettuale e citazioni verificate con ricerca web — da leggere
in originale, non riassunti.

**1.1-1.2 IR classico → rappresentazioni neurali**
TF-IDF, BM25 (Robertson & Sparck Jones), poi il salto a word embeddings
(word2vec, Mikolov et al. 2013) e Transformer:
> Vaswani, A. et al. (2017). *Attention Is All You Need*. NeurIPS 2017.

**1.3 Embedding multilingua**
Da `all-MiniLM-L6-v2` a `paraphrase-multilingual-MiniLM-L12-v2` — scheda
del modello su Hugging Face (sentence-transformers); riferimento fondativo:
> Reimers, N., Gurevych, I. (2019). *Sentence-BERT: Sentence Embeddings
> using Siamese BERT-Networks*. EMNLP 2019.

**1.4 LLM, modelli compatti**
Per Qwen2.5: technical report ufficiale (Qwen Team, Alibaba). Per "modelli
piccoli ≤3B": letteratura su distillazione e quantizzazione.

**1.5 RAG — riferimento fondativo, verificato:**
> Lewis, P. et al. (2020). *Retrieval-Augmented Generation for
> Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
> https://arxiv.org/abs/2005.11401

**1.6 Corrective RAG e Self-RAG — i due implementati nel progetto, riferimenti verificati:**
> Yan, S.-Q. et al. (2024). *Corrective Retrieval Augmented Generation*.
> https://arxiv.org/abs/2401.15884 — corrisponde a `grade_docs` +
> `query_rewriter` nel sistema

> Asai, A. et al. (2023). *Self-RAG: Learning to Retrieve, Generate, and
> Critique through Self-Reflection*. https://arxiv.org/abs/2310.11511 —
> corrisponde a `self_check` nel sistema

**1.7 Valutazione dei sistemi RAG — riferimento verificato:**
> Es, S., James, J., Espinosa Anke, L., Schockaert, S. (2024). *RAGAs:
> Automated Evaluation of Retrieval Augmented Generation*. EACL 2024
> (System Demonstrations), pp. 150-158.
> https://arxiv.org/abs/2309.15217

Per LLM-as-judge in generale: Zheng et al., *"Judging LLM-as-a-judge with
MT-Bench and Chatbot Arena"* (2023) — **non verificato in questa sessione,
controllare prima di citarlo**.

**1.8 RAG sotto vincoli di risorse**
Letteratura su quantizzazione (GGUF/GGML, usata da Ollama) ed edge
inference — area con pochi survey consolidati, da vagliare con cura.

**1.9 Posizionamento**
Da scrivere per ultimo, dopo aver letto 1.1-1.8: qui si spiega cosa
distingue questo lavoro rispetto alla letteratura trovata.

---

## Nota sulle citazioni

Verificate con ricerca web in questa sessione: 1.5 (Lewis et al.), 1.6
(Yan et al., Asai et al.), 1.7 (Es et al.). Non verificato: Zheng et al.
(MT-Bench) — controllare anno, venue ed eventuali co-autori prima di
citarlo in tesi. Tutte le altre indicazioni bibliografiche di questo
documento sono punti di partenza per la ricerca, non citazioni pronte.
