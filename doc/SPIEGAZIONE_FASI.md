# Spiegazione Dettagliata del Progetto RAG per CNI

## Glossario — Cosa significano i termini tecnici

| Termine | Significato |
|---------|-------------|
| **RAG** (Retrieval-Augmented Generation) | Tecnica che combina **recupero** di documenti (retrieval) + **generazione** testo (LLM). Il modello cerca informazioni in un database prima di rispondere, riducendo le allucinazioni. |
| **LLM** (Large Language Model) | Modello di AI che genera testo. Qui usiamo Qwen 2.5 3B via Ollama. |
| **Crawling / Crawler** | Processo che **scarica automaticamente** le pagine web. Il crawler parte dalla homepage del CNI e segue i link ricorsivamente. |
| **Chunk / Chunking** | **Frammentazione** di un documento lungo in pezzi più piccoli (chunk). Ogni chunk viene vettorizzato separatamente per permettere ricerche precise. |
| **Embedding** | **Vettore numerico** (es. 384 numeri) che rappresenta il significato di un testo. Testi simili hanno vettori vicini nello spazio. |
| **Vettore** | Array di numeri che rappresenta un punto in uno spazio multidimensionale. Esempio: `[0.23, -0.45, 0.12, ..., 0.89]` (384 elementi). |
| **Similarità coseno** | Misura di quanto due vettori sono "vicini" (coseno dell'angolo tra loro). Valore da -1 a 1: 1 = identici, 0 = non correlati, -1 = opposti. |
| **Vector Store / Database vettoriale** | Database specializzato nel memorizzare e cercare vettori per similarità. Qui usiamo **Qdrant**. |
| **Indicizzazione (Indexing)** | Processo di inserimento dei chunk vettorizzati nel database vettoriale. |
| **Retrieval** | **Ricerca** dei chunk più simili semanticamente a una domanda. |
| **Reranking** | **Riordinamento** dei risultati del retrieval usando un modello più accurato (cross-encoder) per tenere solo i migliori. |
| **Cross-encoder** | Modello che valuta la **coppia** (domanda, documento) insieme, calcolando un punteggio di pertinenza più preciso del semplice embedding. |
| **Prompt** | **Istruzione** che diamo al LLM per guidare la sua risposta. Include i documenti recovered come contesto. |
| **System prompt** | Messaggio iniziale che definisce il **comportamento** del LLM (es. "rispondi solo basandoti sui documenti forniti"). |
| **LangGraph** | Framework per creare **grafi di elaborazione** a stati. Qui orchestriamo i passaggi del RAG (classifica → recupera → riordina → valuta → genera → verifica → cita). |
| **Corrective RAG** | Variante RAG che **corregge** il retrieval: se i documenti non sono pertinenti, riscrive la query e riprova. Implementato via LangGraph con `grade_docs` + `query_rewriter`. |
| **Self-RAG** | Variante RAG che **autovaluta** la risposta generata. Dopo la generazione, il LLM verifica l'accuratezza e rigenera se trova imprecisioni. |
| **Grade Documents** | Passaggio in cui il LLM valuta se i documenti retrieved contengono informazioni sufficienti per rispondere. Se no, scatta il Corrective RAG. |
| **Query Rewriting** | Riscrittura della domanda utente in forma più specifica per migliorare il retrieval al secondo tentativo. |
| **Temperature** | Parametro del LLM che controlla la **creatività**: bassa (0.2) = risposte precise, alta (1.0) = più creative. |
| **HNSW** (Hierarchical Navigable Small World) | Algoritmo di **indicizzazione vettoriale** che permette ricerche velocissime su milioni di vettori, organizzandoli in una struttura a grafo multi-livello. |
| **Ingestion** | Pipeline completa che va dal caricamento dei documenti fino all'indicizzazione nel database vettoriale. |
| **Pipeline** | Sequenza di passaggi di elaborazione collegati (es. crawl → pulisci → chunk → embed → indicizza). |
| **SSE** (Server-Sent Events) | Protocollo per **streaming** di dati dal server al client. Qui usato per mostrare la risposta del LLM in tempo reale, token dopo token. |
| **Golden dataset** | Insieme di domande di test con **risposte di riferimento** e **fonti attese** note in anticipo. È il "metro di misura" con cui si valuta oggettivamente il sistema: le risposte sono estratte dai documenti reali del corpus, non inventate. (`config/golden_dataset.json`) |
| **Ground truth** | La "verità nota": ciò che il sistema *dovrebbe* rispondere/reperire per una data domanda. |
| **MRR** (Mean Reciprocal Rank) | Metrica di retrieval: media di `1/rank` della prima fonte corretta. Se la fonte giusta è al 1° posto MRR=1; al 5° posto contribuisce 1/5=0.2. |
| **Hit@k** | Frazione di domande in cui almeno una fonte corretta compare nei primi k risultati. Hit@5 = 0.8 significa che su 10 domande, 8 trovano la fonte giusta nei top-5. |
| **LLM-as-judge** | Tecnica di valutazione in cui un LLM fa da "giudice" assegnando punteggi alla risposta generata (qui scala 0-5). Standard nella letteratura RAG quando non è possibile valutare manualmente tutte le risposte. |
| **Faithfulness** (fedeltà) | Metrica qualitativa: la risposta è interamente supportata dai documenti forniti? Intercetta le **allucinazioni**. |
| **Answer relevance** | Metrica qualitativa: la risposta risponde davvero alla domanda posta? Intercetta risposte fuori tema o evasive. |
| **Correctness** (correttezza) | Metrica qualitativa: la risposta è coerente con la verità nota del golden dataset? Intercetta gli **errori fattuali**. |
| **Fallback** | Comportamento di "non so": quando il sistema non trova documenti pertinenti restituisce un messaggio standard invece di inventare una risposta. |
| **PII** (Personally Identifiable Information) | Dati personali sensibili (email, telefono, codice fiscale) che devono essere filtrati prima di essere inviati al LLM o mostrati all'utente. |
| **Boilerplate** | Contenuto ripetitivo delle pagine web (footer, cookie banner, menu) che va rimosso per pulire il testo. |
| **RecursiveCharacterTextSplitter** | Algoritmo di chunking che prova a dividere il testo in punti logici (prima paragrafi, poi frasi, poi parole) per mantenere la coerenza semantica. |

---

## Indice delle Fasi

1. [Configurazione](#1-configurazione-core)
2. [Crawling](#2-crawling)
3. [Filtro Dati Pubblici](#3-filtro-dati-pubblici)
4. [Quality Check](#4-quality-check)
5. [Cleaning](#5-cleaning)
6. [Categorizzazione](#6-categorizzazione)
7. [Chunking](#7-chunking)
8. [Embedding](#8-embedding)
9. [Indicizzazione su Qdrant](#9-indicizzazione-su-qdrant)
10. [Classificazione Query](#10-classificazione-query)
11. [Retrieval Vettoriale](#11-retrieval-vettoriale)
12. [Reranking](#12-reranking)
13. [Prompt Building](#13-prompt-building)
14. [Generazione Risposta (LLM)](#14-generazione-risposta-llm)
15. [Citazioni](#15-citazioni)
16. [API e Frontend](#16-api-e-frontend)
17. [Flusso RAG Chain (LangGraph)](#17-flusso-rag-chain-langgraph)
18. [Valutazione End-to-End](#18-valutazione-end-to-end)

---

## 1. Configurazione (Core)

### File: `src/core/config_loader.py`
**Classe:** `ConfigLoader`

Il progetto carica tutte le configurazioni da file YAML nella cartella `config/`. Usiamo un pattern **Singleton con caching**: la prima volta che un file YAML viene richiesto, viene letto dal disco e tenuto in memoria (`_instances` dict). Le richieste successive restituiscono la versione cached.

```python
class ConfigLoader:
    _instances: dict[str, dict[str, Any]] = {}
```

**Configurazioni caricate:**
- `rag_config.yaml` → parametri chunking, embedding, LLM, retrieval, crawler, qualità
- `qdrant_config.yaml` → modalità (locale/docker), host, porta, dimensione vettori
- `model_config.yaml` → specifiche modelli
- `logging_config.yaml` → logging

**Variabili d'ambiente** (`.env`): possono sovrascrivere le configurazioni YAML. Esempio: `EMBEDDING_MODEL`, `LM_STUDIO_BASE_URL`, `QDRANT_MODE`.

Il file `.env` è caricato automaticamente all'import tramite `load_dotenv()`.

### File: `src/core/model_factory.py`
**Classe:** `ModelFactory`

Factory pattern per creare i due modelli principali:

1. **Embeddings**: usa `HuggingFaceEmbeddings` di LangChain con `paraphrase-multilingual-MiniLM-L12-v2` (12 layer, 50+ lingue). Questo modello trasforma ogni testo in un vettore di 384 dimensioni. Sostituisce `all-MiniLM-L6-v2` per migliore comprensione dell'italiano, mantenendo la stessa dimensione 384.

2. **LLM**: supporta due provider:
   - **Ollama** (default): si connette a `http://localhost:11434/v1` via `ChatOpenAI` di LangChain, usando API compatibile OpenAI. Modello: `qwen2.5:3b`. I parametri (temperature=0.2, max_tokens=2048, top_p=0.95) sono pensati per risposte coerenti e deterministiche.
   - **LlamaCpp**: carica un modello locale via `LlamaCpp`.

### File: `src/core/logging.py`
**Funzione:** `setup_logging()`

Carica `logging_config.yaml`, crea la directory `logs/`, configura handler e formati. Fallback a `basicConfig` se il file non esiste.

---

## 2. Crawling

### File: `src/ingestion/crawler.py`
**Classe:** `CNICrawler`
**Metodo:** `crawl()`

**Cosa facciamo:** Scarichiamo le pagine HTML e i PDF dal sito `www.cni.it` in modo ricorsivo, partendo dalla homepage.

**Dove:** La configurazione del crawler è in `config/rag_config.yaml` → sezione `crawler`.

**Come funziona:**

1. **Code asincrona** (`asyncio.Queue`): partiamo con l'URL base (`https://www.cni.it`) a profondità 0.

2. **5 worker concurrenti**: `asyncio.create_task(self._worker())`. Ogni worker:
   - Prende un URL dalla coda
   - Fa una GET HTTP con `httpx.AsyncClient`
   - Controlla `content-type` della risposta

3. **Per pagine HTML:**
   - Passa l'HTML a `_process_html()` che usa **BeautifulSoup** per:
     - Estrarre il titolo dal `<title>`
     - Eliminare tag inutili (`<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`)
     - Estrarre il testo da `<main>` o `<article>` o `<body>`
     - Scartare pagine con meno di 50 caratteri di contenuto
     - Estrarre meta-tag (description, keywords, ecc.)
   - Poi estrae tutti i link `<a href>` dalla pagina (max 150 link per pagina, da `rag_config.yaml`)
   - Per ogni link, dopo un delay configurabile (default 0.3s), lo aggiunge alla coda con profondità+1

4. **Per PDF:**
   - Usa **PyMuPDF** (`fitz`) per estrarre il testo
   - Scarta se meno di 50 caratteri

5. **Filtri URL** (metodo `_is_allowed()`):
   - Solo domini `www.cni.it` e `cni.it`
   - Blocca: `/wp-admin`, `/wp-json`, `/wp-login`, `/xmlrpc`, `/feed/`, `/en/` (versione inglese del sito, esclusa per focalizzarci su contenuti italiani)
   - Blocca estensioni non testuali: `.xml`, `.css`, `.js`, immagini, video, ecc.
   - `included_paths` configurato: `/media-ing`, `/cni`, `/temi`, `/contatti`, `/servizi` — solo questi path vengono crawlti
   - `priority_paths` con `priority_max_depth: 12` per dare priorità a `/media-ing` e `/cni`

**Perché:** Vogliamo solo contenuti testuali pubblici del CNI. Il crawler è progettato per essere gentile (delay, 5 worker, timeout 30s) e rispettare i limiti di pagine.

**Output:** `list[dict]` con `{url, title, content, meta}` per ogni pagina.

---

## 3. Filtro Dati Pubblici

### File: `src/governance/public_data_filter.py`
**Classe:** `PublicDataFilter`

**Cosa facciamo:** Verifichiamo che ogni documento crawlsito sia effettivamente un dato pubblico.

**Dove:** Chiamato in `scripts/run_ingestion.py` (riga 67) e in `src/api/routes.py` (endpoint `/ingest`).

**Due controlli:**

1. **URL**: blocca path contenenti `/wp-admin`, `/wp-json`, `/wp-login`, `/private`, `/restricted`
2. **Contenuto**: cerca keyword negate come `"credenziali"`, `"non-pubblico"`

**Perché:** Il sito CNI ha sezioni pubbliche (chi-siamo, organi, normativa) e sezioni riservate (login, admin). Vogliamo solo dati pubblici.

---

## 4. Quality Check

### File: `src/governance/quality_check.py`
**Classe:** `QualityChecker`

**Cosa facciamo:** Verifichiamo la qualità del contenuto testuale.

**Quattro controlli:**

1. **Lunghezza minima** (default 50 caratteri): scarta pagine troppo corte (es. redirect, pagine vuote)
2. **Lunghezza massima** (default 100000 caratteri): evita documenti anomali
3. **Repetition Ratio**: calcola `1 - (parole_univoche / parole_totali)`. Se > 0.65 (65% di parole ripetute), scarta. Questo cattura pagine con boilerplate estremo o contenuti generati.
4. **Lingua**: il campo `required_languages: ["it"]` è configurato ma non implementato attivamente (potenziale miglioramento).

**Perché:** Il crawler può raccogliere pagine di bassa qualità, pagine di errore, o pagine con contenuti duplicati. Vogliamo solo testi informativi di qualità.

---

## 5. Cleaning

### File: `src/ingestion/cleaner.py`
**Classe:** `TextCleaner`

**Cosa facciamo:** Puliamo il testo da elementi boilerplate.

**Tre passaggi:**

1. **Rimozione boilerplate** (`_remove_boilerplate`): regex per rimuovere:
   - `© 2024 Tutti i diritti riservati`
   - `Cookie Policy`, `Privacy Policy`, `Informativa sulla privacy`
   - `Termini e condizioni`, `Condizioni d'uso`
   - `Accetta cookie`, `Questo sito utilizza cookie`
   - `Seguici su`, `Condividi su`, `Carica altri`
   - Righe vuote

2. **Normalizzazione spazi** (`_normalize_whitespace`):
   - `\r\n` → `\n`
   - Tab e spazi multipli → spazio singolo
   - Più di 2 newline consecutivi → doppio newline

3. **Rimozione righe duplicate consecutive** (`_remove_repeated_lines`):
   - Tiene traccia delle righe già viste
   - Se una riga (non vuota) è identica a una già apparsa, la rimuove

**Perché:** Le pagine web contengono molto boilerplate (footer, cookie banner, menu). Vogliamo solo il contenuto informativo pulito.

---

## 6. Categorizzazione

### File: `src/governance/public_data_filter.py`
**Metodo:** `categorize(url, content)`

**Cosa facciamo:** Assegnamo una categoria a ogni documento basandoci sull'URL.

**Categorie** (da `ALLOWED_CATEGORIES`):

| Categoria | Match URL |
|-----------|-----------|
| `normativa` | `/normativa` |
| `chi_siamo` | `/chi-siamo` |
| `organi` | `/organi` |
| `commissioni` | `/commissioni` |
| `documenti` | `/documenti` |
| `news` | `/news` |
| `servizi` | `/servizi` |
| `contatti` | `/contatti` |
| `albo` | `/albo` |
| `formazione` | `/formazione` |
| `generico` | nessun match |

**Come:** cerca il nome della categoria (con underscore sostituito da trattino) nell'URL. Se nessuna corrispondenza, assegna `"generico"`.

**Perché:** La categoria viene salvata come metadato nel vector store e usata durante il retrieval per filtrare i risultati per pertinenza (es. se l'utente chiede "organi", cerchiamo solo documenti categorizzati come "organi").

---

## 7. Chunking

### File: `src/ingestion/chunker.py`
**Classe:** `DocumentChunker`

**Cosa facciamo:** Suddividiamo ogni documento in pezzi più piccoli (chunk) per poterli vettorizzare e recuperare efficientemente.

**Configurazione** (da `rag_config.yaml`):
- `chunk_size`: 1500 caratteri (aumentato da 512 per dare più contesto al LLM)
- `chunk_overlap`: 200 caratteri (sovrapposizione tra chunk consecutivi)
- `separators`: `["\n\n", "\n", ".", " ", ""]`

**Come:** Usiamo `RecursiveCharacterTextSplitter` di LangChain. Questo splitter:
1. Prova a dividere per `"\n\n"` (paragrafi)
2. Se il pezzo è ancora troppo grande, prova `"\n"` (righe)
3. Poi `.` (frasi)
4. Poi spazio (parole)
5. Infine carattere per carattere (fallback)

**Output chunk:**
```python
{
    "content": "testo del chunk",
    "metadata": {
        "source": "url originale",
        "title": "titolo documento",
        "chunk_index": 0,      # posizione nel documento
        "total_chunks": 5,     # totale chunk del documento
        "category": "organi"   # categoria assegnata
    }
}
```

**Perché:**
- Chunk da 1500 caratteri danno abbastanza contesto al LLM per capire il documento
- L'overlap (200 caratteri = ~13%) evita di tagliare frasi o concetti a metà
- Il retrieval su chunk è più preciso: cerca nel paragrafo giusto, non nell'intero documento
- I separatori ricorsivi garantiscono che ogni chunk sia quanto più semanticamente coerente possibile

---

## 8. Embedding

### File: `src/ingestion/embedder.py`
**Classe:** `EmbeddingGenerator`

**Cosa facciamo:** Trasformiamo ogni chunk di testo in un vettore numerico (embedding) che cattura il significato semantico del testo.

**Modello:** `paraphrase-multilingual-MiniLM-L12-v2` di **sentence-transformers**

**Caratteristiche:**
- Dimensione output: **384 dimensioni** (vettore di 384 numeri floating-point)
- Layer: 12 (vs 6 del precedente `all-MiniLM-L6-v2`)
- Lingue: 50+ (copertura multilingua significativamente migliore)
- Normalizzazione: attiva (così possiamo usare dot product come similarità)
- Batch: 32 chunk per volta

**Metodi:**
```python
generate(text) -> list[float]           # embedding singolo
generate_batch(texts) -> list[list[float]]  # batch embedding
process_chunks(chunks) -> chunks        # aggiunge campo "embedding" a ogni chunk
```

**Perché `paraphrase-multilingual-MiniLM-L12-v2`?**
- Stessa dimensione 384 del precedente modello — nessuna modifica al database vettoriale
- 12 layer vs 6: comprensione semantica più profonda
- Addestrato su 50+ lingue, con enfasi su traduzioni e parafrasi cross-lingua
- Progettato specificamente per similarità semantica multilingua (perfetto per testi italiani)
- Normalizzato: permette similarità coseno via dot product

**Cosa NON usiamo:** Non usiamo modelli più grandi come `text-embedding-3-large` (OpenAI) perché vogliamo mantenere tutto locale, senza API esterne.

---

## 9. Indicizzazione su Qdrant

### File: `src/vectorstore/qdrant_client.py`
**Classe:** `QdrantClientManager`

**Cosa facciamo:** Creiamo una connessione a Qdrant (database vettoriale) e gestiamo la collezione.

**Modalità (da `qdrant_config.yaml`):**
1. **Locale** (`mode: local`): Qdrant salva i dati su disco in `./data/qdrant_db/`. Usa SQLite embedded.
2. **Docker** (`mode: docker`): si connette a `localhost:6333` (container Qdrant). Necessario per la UI dashboard.

**Configurazione collezione:**
- Nome: `cni_documents`
- Dimensione vettori: 384 (coerente con MiniLM)
- Metrica distanza: **Coseno** (Cosine)
- Indice: **HNSW** (Hierarchical Navigable Small World) con M=16, ef_construct=100
- Optimizer: 2 segmenti, memmap threshold 20000

### File: `src/vectorstore/indexer.py`
**Classe:** `VectorIndexer`

**Cosa facciamo:** Inseriamo i chunk vettorizzati in Qdrant.

```python
def index_chunks(self, chunks) -> int:
```

Per ogni chunk:
1. Genera un UUID come ID univoco
2. Crea un **PointStruct** con:
   - `id`: UUID
   - `vector`: l'embedding (lista di 384 float)
   - `payload`: metadati (content, source, title, chunk_index, category)
3. Esegue `upsert` sul database (insert o update se esiste già)

**Altri metodi:**
- `count_points()`: quanti vettori sono indicizzati
- `clear_index()`: cancella e ricrea la collezione

**Perché Qdrant?**
- Database vettoriale open-source
- Supporta similarità coseno nativamente
- Filtri sui payload (category, source) integrati
- HNSW index per ricerca approssimata veloce (anni vs lineare)
- Può girare 100% locale senza Docker

**Stato attuale:** 5890 documenti crawlti → 17098 chunk indicizzati nella collezione `cni_documents`.

---

## 10. Classificazione Query

### File: `src/rag/query_classifier.py`
**Classe:** `QueryClassifier`

**Cosa facciamo:** Quando l'utente fa una domanda, classifichiamo semanticamente di cosa parla.

**Metodo:** keyword matching pesato

```python
CATEGORIES = {
    "normativa": ["normativa", "legge", "decreto", "regolamento", "codice", "articolo"],
    "organi": ["organo", "consiglio", "presidente", "vicepresidente", "segretario", "tesoriere"],
    "commissioni": ["commissione", "comitato", "gruppo", "tavolo"],
    "albo": ["albo", "elenco", "iscrizione", "registro", "ingegnere", "professione"],
    "formazione": ["formazione", "credito", "cfp", "corso", "aggiornamento", "seminario"],
    "servizi": ["servizio", "sportello", "assistenza", "modello", "domanda"],
    "documenti": ["documento", "bilancio", "relazione", "verbale", "delibera"],
    "contatti": ["contatto", "sede", "telefono", "email", "pec", "indirizzo"],
}
```

**Algoritmo:**
1. Converte la query in lowercase
2. Per ogni categoria, conta quante keyword sono presenti nella query
3. Se nessuna keyword matcha → `"generico"`
4. Altrimenti → categoria con più match

**Esempio:**
- Query: "Quali sono gli organi del CNI e chi è il presidente?"
- Match: `organi` (organo, presidente = 2), potrebbe matchare anche `commissioni` (0)
- Risultato: `"organi"`

**Perché:**
- Semplice, veloce, non richiede un modello ML
- Ci permette di filtrare il retrieval per categoria (es. se chiede "organi", cerchiamo solo chunk con category="organi")
- Riduce il rumore nei risultati retrieved

---

## 11. Retrieval Vettoriale

### File: `src/vectorstore/retriever.py`
**Classe:** `VectorRetriever`

**File:** `src/rag/hybrid_retriever.py`
**Classe:** `HybridRetriever`

**Cosa facciamo:** Cerchiamo i chunk più simili semanticamente alla domanda dell'utente.

### Il processo completo:

**Passo 1 — HybridRetriever.retrieve():**
1. Classifica la query con `QueryClassifier`
2. Se la categoria non è `"generico"`, crea un filtro Qdrant: `{"category": "organi"}`
3. Chiama `VectorRetriever.retrieve()` con il filtro

**Passo 2 — VectorRetriever.retrieve():**
1. **Embedding della query:** converte la domanda in un vettore di 384 dimensioni usando lo stesso modello di embedding
2. **Ricerca in Qdrant:** chiama `client.query_points()` con:
   - `query`: il vettore della domanda
    - `limit`: `top_k` (default 20)
    - `score_threshold`: 0.3 (scarta risultati con similarità < 0.3)
   - `query_filter`: filtro per categoria (se presente)

3. **Calcolo similarità:** Qdrant usa la **distanza coseno**:

   ```
   cosine_similarity(A, B) = cos(θ) = (A · B) / (||A|| * ||B||)
   ```

   Dove:
   - A = vettore della query
   - B = vettore del chunk
   - `A · B` = prodotto scalare (somma degli elementi moltiplicati)
   - `||A||` = norma (radice quadrata della somma dei quadrati)

   Poiché i vettori sono normalizzati (norma = 1), la distanza coseno equivale al **prodotto scalare**:
   ```
   cosine_similarity = A · B = Σ(A[i] * B[i])
   ```

   Qdrant restituisce un `score` (valore tra -1 e 1, ma tipicamente 0-1 con vettori normalizzati positivi). Più alto = più simile.

4. **Filtro threshold:** risultati con score < 0.3 vengono scartati
5. **Risultato:** lista di dict con `{content, source, title, score, chunk_index, category}`

**Perché "ibrido":** Il termine "ibrido" si riferisce alla combinazione di:
- **Filtro categorico** (basato su keyword matching sulla query)
- **Ricerca vettoriale** (basata su similarità semantica)

Non è un vero hybrid search BM25 + vettoriale (non implementiamo sparse retrieval), ma l'approccio è comunque efficace perché restringe il dominio prima della ricerca semantica.

**Perché score_threshold = 0.3?** Per evitare di escludere documenti rilevanti con similarità moderata. Con embedding multilingua, documenti italiani validi possono avere score tra 0.3 e 0.5. Una soglia a 0.5 li escludeva ingiustamente.

---

## 12. Reranking

### File: `src/rag/reranker.py`
**Classe:** `Reranker`

**Cosa facciamo:** Riordiniamo i risultati del retrieval usando un cross-encoder per selezionare solo i documenti più pertinenti da passare al LLM.

**Stato attuale:** Il reranker è **abilitato** (`enabled: true`). Prende i `top_k=10` documenti dal retrieval vettoriale, li riordina con il cross-encoder, e mantiene i `top_k=5` finali.

**Come funziona:**
- Il bi-encoder (usato nel retrieval) codifica query e documento separatamente, poi calcola similarità coseno tra i due vettori. Veloce ma meno preciso.
- Il cross-encoder prende la **coppia** (query, documento) in un unico forward pass, calcolando un punteggio di rilevanza diretto. Più lento (O(n) per n documenti) ma più accurato.

**Processo:**
1. Riceve ~10 documenti dal retrieval vettoriale
2. Per ogni documento, crea una coppia `(query, content)`
3. Il cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) predice uno score di pertinenza per ogni coppia
4. Ordina i documenti per score decrescente
5. Mantiene solo i top `top_k=5`

**Perché abilitato:** Il cross-encoder, pur essendo allenato su inglese, aiuta a selezionare i documenti più pertinenti dal pool di 10 retrieved, riducendo il rumore nei 5 documenti finali inviati al LLM. Il grade_docs successivo (Corrective RAG) funge da ulteriore filtro di qualità.

---

## 13. Prompt Building

### File: `src/rag/prompt_builder.py`
**Classe:** `PromptBuilder`

**Cosa facciamo:** Costruiamo il prompt (messaggio) da inviare al LLM, combinando la domanda dell'utente con i documenti retrieved.

**Template system:**
```
Sei un assistente specializzato nella consultazione dei dati pubblici 
del Consiglio Nazionale degli Ingegneri (CNI).

Utilizza SOLO i documenti forniti nel contesto per rispondere.
Se i documenti non contengono informazioni sufficienti, dillo chiaramente.

Linee guida:
- Rispondi sempre in ITALIANO
- Cita le fonti usando [Fonte: titolo documento]
- Se un'informazione non è presente nei documenti, NON inventarla

Documenti di riferimento:
[Documento 1 - Titolo]
Fonte: URL
Contenuto del chunk...

[Documento 2 - Titolo]
Fonte: URL
Contenuto del chunk...

Domanda: {domanda dell'utente}
```

**Output:** lista di due messaggi nel formato ChatGPT/OpenAI:
```python
[
    {"role": "system", "content": "Sei un assistente..."},
    {"role": "user", "content": "Quali sono gli organi del CNI?"}
]
```

**Streaming:** `build_stream_prompt()` restituisce una singola stringa (non separata in system/user) perché alcuni LLM in streaming usano un formato diverso.

**Perché:**
- Il system prompt forza il LLM a usare SOLO i documenti forniti (evita allucinazioni)
- Le citazioni nel prompt istruiscono il LLM a referenziare le fonti
- La struttura contesto + domanda è il pattern standard del RAG

---

## 14. Generazione Risposta (LLM)

### File: `src/inference/llm_client.py`
**Classe:** `LLMClient`

### File: `src/inference/response_generator.py`
**Classe:** `ResponseGenerator`

**Cosa facciamo:** Inviamo il prompt al LLM (Qwen 2.5 3B via Ollama) e otteniamo la risposta.

**Pipeline:**
1. **PII Filter** (in `rag_chain.py`): prima di inviare il prompt, filtriamo ogni messaggio con `PIIFilter` per rimuovere dati sensibili (email, telefoni, codici fiscali, partite IVA)
2. **Conversione messaggi** (`LLMClient`): da formato `{role, content}` a oggetti LangChain (`SystemMessage`, `HumanMessage`)
3. **Invio al LLM:** chiamata `llm.invoke(messages)` per risposta sincrona, o `llm.stream()` per streaming token-by-token

**Parametri LLM:**
- `temperature`: 0.2 (bassa = risposte più deterministiche, meno creative)
- `max_tokens`: 2048 (lunghezza massima risposta)
- `top_p`: 0.95 (nucleus sampling)
- `frequency_penalty`: 0
- `presence_penalty`: 0

**Provider: Ollama** su `http://localhost:11434/v1`. Ollama carica il modello `qwen2.5:3b` localmente e fornisce un'API compatibile con OpenAI.

**Streaming asincrono** (`astream_generate`):
- Usa un sync generator per lo streaming (LangChain non supporta nativamente async stream per tutti i modelli)
- Esegue `next(sync_gen)` in un thread pool (`run_in_executor`) per non bloccare l'event loop
- Ogni chunk viene filtrato per PII prima di essere inviato al client

**Perché:**
- Qwen 2.5 3B è un modello piccolo, veloce e gira su laptop con 8GB RAM
- Ollama evita di esporre dati a API esterne (tutto locale)
- Temperature bassa per risposte fattuali (non creative)
- Streaming per UX migliore (l'utente vede la risposta mentre viene generata)

---

## 15. Citazioni

### File: `src/inference/citation_builder.py`
**Classe:** `CitationBuilder`

**Cosa facciamo:** Costruiamo la lista delle fonti (citazioni) da mostrare all'utente insieme alla risposta.

**Metodo:** `build(documents, response)`

Per ogni documento rerankato:
1. Salta documenti senza source URL
2. Crea un dict con:
   - `title`: titolo del documento (o ultimo segmento dell'URL)
   - `source`: URL completo
   - `relevance_score`: score (da 0 a 1)
   - `excerpt`: i primi ~200 caratteri del contenuto (tagliato all'ultimo spazio)
3. Deduplica per nome file (stesso URL base → una citazione)

**Output:** `list[CitationResponse]`
```json
[
    {
        "title": "Organi CNI",
        "source": "https://www.cni.it/organi",
        "relevance_score": 0.9234,
        "excerpt": "Il Consiglio Nazionale degli Ingegneri è composto dal Presidente, dal Consiglio di Presidenza..."
    }
]
```

**Perché:** Le citazioni sono fondamentali per:
- Trasparenza (l'utente sa da dove arrivano le informazioni)
- Verificabilità (può cliccare e controllare)
- Credibilità (mostra che la risposta è basata su fonti reali)

---

## 16. API e Frontend

### File: `src/api/main.py`
**App FastAPI:**
- CORS configurato per `http://localhost:4200` (Angular)
- Tutti gli endpoint sotto prefix `/api/v1`
- Endpoint di startup/shutdown logging

### File: `src/api/routes.py`
**Router FastAPI:**
| Metodo | Path | Descrizione |
|--------|------|-------------|
| POST | `/api/v1/query` | Query RAG standard (sincrona) |
| POST | `/api/v1/query/stream` | Query in streaming SSE |
| GET | `/api/v1/health` | Stato del sistema |
| POST | `/api/v1/ingest` | Pipeline completa di ingestion |

**POST /api/v1/query:**
1. Prende `{"question": "..."}` dal body
2. Ottiene o crea il singleton `RAGChain`
3. Chiama `chain.query(question)` che esegue l'intero grafo LangGraph
4. Restituisce `{response, citations, category, trace_id}`

**POST /api/v1/query/stream:**
- Usa Server-Sent Events (SSE)
- Eventi:
  - `metadata`: categoria e fonti retrieve
  - `chunk`: token della risposta (incrementale)
  - `done`: citazioni finali e trace_id

**GET /api/v1/health:**
- Verifica connessione a Qdrant (conta punti)
- Verifica connessione a LLM (invio messaggio test)
- Restituisce `{status, version, documents_indexed, llm_connected}`

**POST /api/v1/ingest:**
- Esegue l'intera pipeline: crawl → filtri → clean → chunk → embed → index
- Restituisce riepilogo: `{status, documents_crawled, chunks_indexed}`

### File: `src/api/schemas.py`
Modelli Pydantic per validazione request/response:
- `QueryRequest`: `{question: str (1-2000), top_k?: int (1-20)}`
- `QueryResponse`: `{response, citations[], category, trace_id}`
- `CitationResponse`: `{title, source, relevance_score, excerpt}`
- `HealthResponse`: `{status, version, documents_indexed, llm_connected}`
- `IngestResponse`: `{status, documents_crawled, chunks_indexed, message}`

### Frontend Angular
Directory `frontend/`:
- **chat.component.ts**: componente chat con input, storico messaggi, typing indicator, citazioni cliccabili
- **rag.service.ts**: servizio HTTP per chiamare API (query, health, ingest, streaming via XHR con `onprogress`)
- **rag.models.ts**: interfacce TypeScript (QueryResponse, Citation, ChatMessage, StreamEvent)
- **app.component.ts**: root con header e LED health status

---

## 17. Flusso RAG Chain (LangGraph)

### File: `src/rag/rag_chain.py`
**Classe:** `RAGChain`

**Cosa facciamo:** Orchestriamo l'intero flusso RAG usando **LangGraph**, un framework per costruire grafi di stato con archi condizionali.

**Il grafo (9 nodi, 3 archi condizionali):**

```
                    ┌─────────────────────────────────────────────┐
                    │                    START                    │
                    │              classify (QueryClassifier)     │
                    └─────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────┐
                    │              retrieve (HybridRetriever)     │
                    └─────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────┐
                    │              rerank (Cross-Encoder)          │
                    │              top_k 10 → top_k 5             │
                    └─────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────┐
                    │           grade_docs (Qwen valuta)          │
                    └──────────────┬──────────────────┬───────────┘
                                   │                  │
                             pertinente         non pertinente
                                   │                  │
                                   │    ┌─────────────▼───────────┐
                                   │    │  rewrite_query (Qwen)   │
                                   │    └─────────────┬───────────┘
                                   │                  │
                                   │            retry_count ≤ 1?
                                   │              ┌────┴────┐
                                   │            retry    fallback
                                   │              │          │
                                   │    ┌─────────▼──┐  ┌────▼────┐
                                   │    │  retrieve  │  │ fallback │
                                   │    │  → rerank  │  │ → END   │
                                   │    │  → grade   │  └─────────┘
                                   │    └─────────┬──┘
                                   │         pertinente
                                   │              │
                    ┌───────────────┴──────────────┘
                    │
      ┌─────────────▼──────────────────┐
      │     build_prompt (PromptBuilder)│
      └─────────────┬──────────────────┘
                    │
      ┌─────────────▼──────────────────┐
      │  generate (PIIFilter + Qwen)   │
      └─────────────┬──────────────────┘
                    │
      ┌─────────────▼──────────────────┐
      │   self_check (Qwen valuta)     │
      └─────────────┬──────────────────┘
                    │
              ┌─────┴────┐
          accurata   inaccurata + !fix_attempted
              │              │
              │    ┌─────────▼──────────┐
              │    │  generate (fix)    │
              │    └─────────┬──────────┘
              │              │
              │    ┌─────────▼──────────┐
              │    │  self_check (no)   │
              │    │  → accurata        │
              │    └────────────────────┘
              │
      ┌───────▼──────────────────────┐
      │  build_citations (Citation)  │
      └──────────────┬───────────────┘
                     │
                [END] - RISPOSTA
```

**Stato (RAGState):**
```python
{
    "question": str,              # domanda utente (può essere riscritta)
    "category": str,              # categoria classificata
    "retrieved_docs": list,       # documenti retrieved
    "reranked_docs": list,        # documenti riordinati
    "prompt": list,               # messaggi prompt [{role, content}]
    "response": str,              # risposta LLM
    "citations": list,            # citazioni
    "trace_id": str,              # ID univoco per tracing
    "fallback_triggered": bool,  # se True, risposta = messaggio fallback
    "grade_result": str,          # "pertinente" | "non pertinente"
    "retry_count": int,           # 0, 1, 2 (max 1 rewrite + retry)
    "self_check_result": str,     # "accurata" | "inaccurata"
    "fix_attempted": bool,        # True dopo 1 tentativo di fix
}
```

**Ogni nodo:**
1. **classify** → `QueryClassifier.classify()` + log monitoring
2. **retrieve** → `HybridRetriever.retrieve(query)` — top_k=10
3. **rerank** → `Reranker.rerank(query, docs)` — cross-encoder → top_k=5
4. **grade_docs** → `GradeDocs.grade(question, docs)` — LLM valuta se docs sono pertinenti
5. **rewrite_query** → `QueryRewriter.rewrite(question)` — LLM riscrive query per retry
6. **build_prompt** → `PromptBuilder.build_prompt(question, docs)` — costruisce system + user
7. **generate** → filtra PII, chiama `ResponseGenerator.generate(prompt)`; se fix_attempted, aggiunge istruzione di correzione
8. **self_check** → `SelfRAG.check(question, response, docs)` — LLM valuta accuratezza
9. **build_citations** → `CitationBuilder.build(docs, response)`
10. **fallback** → restituisce messaggio "Non ho trovato informazioni sufficienti..."

**Archi condizionali (decisioni automatiche del grafo):**
- `grade_docs` → `"pertinente"` → `build_prompt`; `"non pertinente"` → `rewrite_query`
- `rewrite_query` → `retry_count <= 1` → `retrieve` (retry con query riscritta); altrimenti → `fallback`
- `self_check` → `"accurata"` → `build_citations`; `"inaccurata" + !fix_attempted` → `generate` (con fix prompt)

**Metodi pubblici:**
- `query(question)` → esecuzione sincrona del grafo (invoke del LangGraph)
- `astream(question)` → generator asincrono per streaming SSE (non usa LangGraph, esegue i passi manualmente per avere controllo sullo streaming token-by-token)

**Perché Corrective RAG + Self-RAG?**
1. **Corrective RAG**: se i documenti retrieved non sono pertinenti, riscriviamo la query e riproviamo una volta. Questo recupera domande che al primo tentativo non trovavano risposta.
2. **Self-RAG**: dopo la generazione, il LLM valuta la propria risposta. Se trova imprecisioni, rigenera con un'istruzione di correzione. Questo riduce le allucinazioni.
3. **Limite di 1 retry e 1 fix**: evitiamo loop infiniti. Se al secondo tentativo non trova documenti, va in fallback. Se il fix non basta, la risposta viene comunque inviata.

### Nuovi moduli RAG

### `src/rag/grade_docs.py` — `GradeDocs`

**Cosa facciamo:** Valutiamo se i documenti retrieved contengono informazioni sufficienti per rispondere alla domanda.

**Come:** Chiediamo a Qwen 2.5 3B di classificare la pertinenza dei documenti, con un prompt specifico:

```
Sei un valutatore di rilevanza. Data una domanda e un insieme di documenti,
determina se i documenti contengono informazioni sufficienti per rispondere.
Rispondi solo con 'pertinente' o 'non pertinente'.
```

**Output:** una stringa: `"pertinente"` o `"non pertinente"`.

### `src/rag/query_rewriter.py` — `QueryRewriter`

**Cosa facciamo:** Riscriviamo la domanda utente in forma più specifica per migliorare il retrieval quando grade_docs fallisce.

**Come:** Chiediamo a Qwen di riscrivere la query:

```
Riscrivi la seguente domanda in modo più specifico e dettagliato per migliorare
la ricerca nei documenti. Mantieni il significato originale ma aggiungi contesto.
```

**Output:** stringa riscritta (es. "organi del CNI" → "quali sono gli organi istituzionali del Consiglio Nazionale degli Ingegneri e quali funzioni svolgono").

### `src/rag/self_rag.py` — `SelfRAG`

**Cosa facciamo:** Valutiamo l'accuratezza della risposta generata confrontandola con i documenti originali.

**Come:** Chiediamo a Qwen di verificare:

```
Confronta la risposta con i documenti forniti. Identifica eventuali affermazioni
non supportate, inesattezze o allucinazioni. Rispondi solo con 'accurata' o 'inaccurata'.
```

**Se inaccurata:** rigeneriamo la risposta aggiungendo al system prompt: *"La risposta precedente conteneva imprecisioni o allucinazioni. Correggi basandoti ESCLUSIVAMENTE sui documenti forniti. Non inventare nulla."*

**Limite:** 1 solo tentativo di correzione. Se ancora inaccurata, la risposta viene comunque inviata.

### File: `src/governance/pii_filter.py`
**Classe:** `PIIFilter`

**Cosa facciamo:** Filtriamo dati personali da domande e risposte prima che arrivino al LLM o all'utente.

**Pattern:**
- Email: `nome@dominio.com`
- Telefono: numeri con prefisso
- Codice Fiscale: formato italiano (ABCDEF12G34H567I)
- Partita IVA: IT + 11 cifre
- SSN: formato americano

**Opzioni:**
- `enabled`: attiva/disattiva
- `masked`: sostituisce con `[EMAIL_REDACTED]` (se True) o rimuove (se False)

**Dove viene applicato:**
1. Sul prompt prima di inviarlo al LLM (method `_generate` in `rag_chain.py`)
2. Su ogni chunk della risposta in streaming (`astream` in `rag_chain.py`)

### File: `src/governance/monitoring.py`
**Classe:** `RAGMonitor`

Tracciamento richieste con timing. Crea una traccia per ogni query con:
- UUID univoco
- Timestamp inizio/fine
- Eventi intermedi con dati (classify, retrieve, grade_docs, rewrite, generate, self_check)
- Durata in millisecondi

---

## 18. Valutazione End-to-End

### File: `config/golden_dataset.json`, `benchmarks/run_evaluation.py`

Questa fase **non partecipa alla risposta** ma misura oggettivamente quanto
bene il sistema risponde. È la parte su cui si costruiscono i risultati
sperimentali della tesi.

### Perché serve

Le metriche di solo-retrieval con keyword matching possono essere alte anche
quando il sistema non sa rispondere (es. un chunk che contiene la parola
"presidente" in una news qualsiasi fa salire l'MRR senza contenere la risposta).
La valutazione end-to-end controlla invece il **ciclo completo**: retrieval →
rerank → generazione, confrontando l'output con una verità nota.

### Il golden dataset

`config/golden_dataset.json` contiene domande di test con:
- `reference_answer`: risposta corretta, **estratta dai documenti reali** del corpus
- `expected_sources`: le pagine da cui la risposta dovrebbe venire
- `must_contain`: fatti chiave che la risposta finale deve citare

### Come funziona l'harness

Per ogni domanda il run_evaluation.py:

1. Invia la domanda all'API (`POST /query`) — pipeline completa reale
2. Calcola le metriche di retrieval confrontando i documenti recuperati con le `expected_sources`
3. Fa valutare la risposta a un LLM giudice (qwen2.5:3b) su tre assi 0-5:
   - **Faithfulness**: la risposta è supportata dai documenti? (niente allucinazioni)
   - **Answer relevance**: risponde alla domanda?
   - **Correctness**: è coerente con la risposta di riferimento?
4. Verifica i `must_contain` e registra latenza e fallback
5. Salva tutto: dettaglio per giorno (`results/YYYY-MM-DD/`), storico cumulativo
   (`history.csv`, `summary.csv`) e checkpoint per riprendere run interrotti

### Perché è utile per la tesi

- **Numeri dimostrabili**: tabelle Hit@k / MRR / fedeltà / correttezza prima e dopo ogni modifica
- **Analisi degli errori**: ogni run conserva risposta completa, fonti recuperate
  e punteggi per domanda — permette di dire *perché* il sistema ha sbagliato
- **Tracciabilità temporale**: i risultati sono organizzati per data, quindi ogni
  sessione sperimentale è confrontabile nel tempo (`summary.csv`)

---

## Riepilogo: il Viaggio di una Query

Ecco cosa succede quando un utente chiede "Quali sono gli organi del CNI?":

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  UTENTE: "Quali sono gli organi del CNI?"                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  1. API (routes.py) riceve la richiesta POST /api/v1/query                      │
│  2. RAGChain.query() inizia la traccia monitoring                               │
│                                                                                  │
│  3. CLASSIFY (query_classifier.py)                                               │
│     → keyword matching trova "organi" + "consiglio" → categoria "organi"        │
│                                                                                  │
│  4. RETRIEVE (hybrid_retriever.py + vectorstore/retriever.py)                   │
│     → embedding della query con MiniLM → vettore 384 dim                        │
│     → filtro Qdrant: category="organi"                                           │
│     → search in Qdrant con similarità coseno                                     │
│     → top 25 risultati con score > 0.3 (candidati per il reranker)              │
│                                                                                  │
│  5. RERANK (reranker.py)                                                         │
│     → cross-encoder multilingue BAAI/bge-reranker-base                          │
│     → riscore le coppie (domanda, chunk) e mantiene i top 5                     │
│                                                                                  │
│  6. BUILD PROMPT (prompt_builder.py)                                             │
│     → costruisce system prompt con i 5 documenti selezionati come contesto      │
│     → formato: [Documento 1 - titolo] \n Fonte: URL \n contenuto...             │
│                                                                                  │
│  7. GENERATE (llm_client.py + response_generator.py)                            │
│     → filtra PII dal prompt                                                      │
│     → invia a Qwen 2.5 3B via Ollama (localhost:11434)                          │
│     → temperatura 0.2 → risposta deterministica                                 │
│                                                                                  │
│  8. CITATIONS (citation_builder.py)                                              │
│     → costruisce lista fonti con excerpt e score                                │
│                                                                                  │
│  RISPOSTA: {                                                                     │
│    "response": "Il Consiglio Nazionale degli Ingegneri è composto da...",        │
│    "citations": [{"title": "...", "source": "https://www.cni.it/organi", ...}], │
│    "category": "organi",                                                         │
│    "trace_id": "uuid"                                                            │
│  }                                                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Metriche Chiave per la Presentazione

| Aspetto | Valore | Perché |
|---------|--------|--------|
| Dimensione embedding | 384 | Multilingual MiniLM L12 - bilancia accuracy/velocità |
| Similarità | Coseno | Standard per embedding normalizzati |
| chunk_size | 1500 | Più contesto per il LLM, chunk più significativi |
| chunk_overlap | 200 (13%) | Evita tagli netti nel testo |
| top_k retrieval | 25 | Recupera più candidati; il reranker multilingue seleziona i migliori |
| reranker | BAAI/bge-reranker-base | Cross-encoder **multilingue**: ordina correttamente anche testi italiani |
| score_threshold | 0.3 | Soglia più bassa per non perdere documenti rilevanti |
| Temperature LLM | 0.2 | Risposte fattuali e precise |
| Max pagine crawl | 5000 | Copertura completa del sito CNI |
| Profondità crawl | 5 | Homepage → sezioni → sottosezioni → pagine |
