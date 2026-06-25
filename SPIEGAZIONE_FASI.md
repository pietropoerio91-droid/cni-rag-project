# Spiegazione Dettagliata del Progetto RAG per CNI

## Glossario — Cosa significano i termini tecnici

| Termine | Significato |
|---------|-------------|
| **RAG** (Retrieval-Augmented Generation) | Tecnica che combina **recupero** di documenti (retrieval) + **generazione** testo (LLM). Il modello cerca informazioni in un database prima di rispondere, riducendo le allucinazioni. |
| **LLM** (Large Language Model) | Modello di AI che genera testo. Qui usiamo modelli open-source via LM Studio (es. Llama 3.2, Mistral 7B). |
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
| **LangGraph** | Framework per creare **grafi di elaborazione** a stati. Qui orchestriamo i passaggi del RAG (classifica → recupera → riordina → genera). |
| **Temperature** | Parametro del LLM che controlla la **creatività**: bassa (0.2) = risposte precise, alta (1.0) = più creative. |
| **HNSW** (Hierarchical Navigable Small World) | Algoritmo di **indicizzazione vettoriale** che permette ricerche velocissime su milioni di vettori, organizzandoli in una struttura a grafo multi-livello. |
| **Ingestion** | Pipeline completa che va dal caricamento dei documenti fino all'indicizzazione nel database vettoriale. |
| **Pipeline** | Sequenza di passaggi di elaborazione collegati (es. crawl → pulisci → chunk → embed → indicizza). |
| **SSE** (Server-Sent Events) | Protocollo per **streaming** di dati dal server al client. Qui usato per mostrare la risposta del LLM in tempo reale, token dopo token. |
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

1. **Embeddings**: usa `HuggingFaceEmbeddings` di LangChain con `all-MiniLM-L6-v2`. Questo modello trasforma ogni testo in un vettore di 384 dimensioni. Può eseguire su CPU o GPU.

2. **LLM**: supporta due provider:
   - **LM Studio** (default): si connette a `http://localhost:1234/v1` via `ChatOpenAI` di LangChain, usando la stessa API di OpenAI. I parametri (temperature=0.2, max_tokens=2048, top_p=0.95) sono pensati per risposte coerenti e deterministiche.
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
   - Poi estrae tutti i link `<a href>` dalla pagina (max 50 link per pagina)
   - Per ogni link, dopo un delay configurabile (default 0.3s), lo aggiunge alla coda con profondità+1

4. **Per PDF:**
   - Usa **PyMuPDF** (`fitz`) per estrarre il testo
   - Scarta se meno di 50 caratteri

5. **Filtri URL** (metodo `_is_allowed()`):
   - Solo domini `www.cni.it` e `cni.it`
   - Blocca: `/wp-admin`, `/wp-json`, `/wp-login`, `/xmlrpc`, `/feed/`
   - Blocca estensioni non testuali: `.xml`, `.css`, `.js`, immagini, video, ecc.
   - Se `included_paths` è configurato, filtra solo quei path

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
3. **Repetition Ratio**: calcola `1 - (parole_univoche / parole_totali)`. Se > 0.3 (30% di parole ripetute), scarta. Questo cattura pagine con boilerplate estremo o contenuti generati.
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
- I modelli di embedding lavorano meglio su testi brevi (512 caratteri è ideale per MiniLM)
- L'overlap (64 caratteri = ~12.5%) evita di tagliare frasi o concetti a metà
- Il retrieval su chunk piccoli è più preciso: cerca nel paragrafo giusto, non nell'intero documento
- I separatori ricorsivi garantiscono che ogni chunk sia quanto più semanticamente coerente possibile

---

## 8. Embedding

### File: `src/ingestion/embedder.py`
**Classe:** `EmbeddingGenerator`

**Cosa facciamo:** Trasformiamo ogni chunk di testo in un vettore numerico (embedding) che cattura il significato semantico del testo.

**Modello:** `paraphrase-multilingual-MiniLM-L12-v2` di **sentence-transformers**

**Caratteristiche:**
- Dimensione output: **384 dimensioni** (vettore di 384 numeri floating-point)
- Normalizzazione: attiva (così possiamo usare dot product come similarità)
- Batch: 32 chunk per volta
- **Multilingua**: supporta italiano, molto meglio del precedente `all-MiniLM-L6-v2` (modello solo inglese)

**Metodi:**
```python
generate(text) -> list[float]           # embedding singolo
generate_batch(texts) -> list[list[float]]  # batch embedding
process_chunks(chunks) -> chunks        # aggiunge campo "embedding" a ogni chunk
```

**Perché `all-MiniLM-L6-v2`?**
- Efficiente (6 layer, modello piccolo): gira su CPU in pochi ms
- 384 dimensioni è un buon compromesso tra accuratezza e velocità
- Supporta italiano bene (addestrato su dati multilingua)
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
1. **Embedding della query:** converte la domanda in un vettore di 384 dimensioni usando lo stesso modello `all-MiniLM-L6-v2`
2. **Ricerca in Qdrant:** chiama `client.query_points()` con:
   - `query`: il vettore della domanda
   - `limit`: `top_k` (default 5)
   - `score_threshold`: 0.5 (scarta risultati con similarità < 0.5)
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

4. **Filtro threshold:** risultati con score < 0.5 vengono scartati
5. **Risultato:** lista di dict con `{content, source, title, score, chunk_index, category}`

**Perché "ibrido":** Il termine "ibrido" si riferisce alla combinazione di:
- **Filtro categorico** (basato su keyword matching sulla query)
- **Ricerca vettoriale** (basata su similarità semantica)

Non è un vero hybrid search BM25 + vettoriale (non implementiamo sparse retrieval), ma l'approccio è comunque efficace perché restringe il dominio prima della ricerca semantica.

**Perché score_threshold = 0.5?** Per evitare di restituire documenti non pertinenti. Se nessun documento supera 0.5, la risposta sarà basata solo sul prompt system, e il LLM dirà di non avere informazioni sufficienti.

---

## 12. Reranking

### File: `src/rag/reranker.py`
**Classe:** `Reranker`

**Cosa facciamo:** Riordiniamo i risultati del retrieval usando un modello più preciso per migliorare la qualità.

**Problema:** Il retrieval vettoriale con MiniLM è veloce ma approssimativo. Calcola la similarità tra la query e ogni chunk in modo indipendente, ma non considera la **relazione incrociata** tra query e chunk.

**Soluzione:** Usiamo un **cross-encoder**: `cross-encoder/ms-marco-MiniLM-L-6-v2`.

**Come funziona un cross-encoder?**
- Invece di codificare separatamente query e documento (come fa il bi-encoder MiniLM), il cross-encoder prende la **coppia** (query, documento) in un unico forward pass
- Calcola un punteggio di rilevanza diretto, più accurato
- Svantaggio: è più lento (O(n) per n documenti, mentre il bi-encoder è O(1) per la query + O(n) per similarità vettoriale)

**Processo:**
1. Per ogni documento retrieved, crea una coppia `(query, content)`
2. Il cross-encoder predice un punteggio per ogni coppia
3. Ordina i documenti per punteggio decrescente
4. Mantiene solo i top `top_k` (default 3)

**Fallback:** Se il cross-encoder non è disponibile (errore di caricamento), ordina per score vettoriale.

**Perché:** Migliora la precisione. Dei 5 documenti retrieved, solo i 3 più pertinenti passano al LLM. Questo riduce il rumore nel contesto e migliora la qualità della risposta.

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

**Cosa facciamo:** Inviamo il prompt al LLM (Llama 3.2 via LM Studio) e otteniamo la risposta.

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

**Provider: LM Studio** su `http://localhost:1234/v1`. LM Studio carica il modello `llama-3.2-3b-instruct` localmente e fornisce un'API compatibile con OpenAI.

**Streaming asincrono** (`astream_generate`):
- Usa un sync generator per lo streaming (LangChain non supporta nativamente async stream per tutti i modelli)
- Esegue `next(sync_gen)` in un thread pool (`run_in_executor`) per non bloccare l'event loop
- Ogni chunk viene filtrato per PII prima di essere inviato al client

**Perché:**
- Llama 3.2 3B è un modello piccolo, veloce e gira su laptop
- LM Studio evita di esporre dati a API esterne (tutto locale)
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

**Cosa facciamo:** Orchestriamo l'intero flusso RAG usando **LangGraph**, un framework per costruire grafi di stato.

**Il grafo:**

```
classify ──► retrieve ──► rerank ──► build_prompt ──► generate ──► build_citations ──► END
```

**Stato (RAGState):**
```python
{
    "question": str,           # domanda utente
    "category": str,           # categoria classificata
    "retrieved_docs": list,    # documenti retrieved
    "reranked_docs": list,     # documenti riordinati
    "prompt": list,            # messaggi prompt [{role, content}]
    "response": str,           # risposta LLM
    "citations": list,         # citazioni
    "trace_id": str,           # ID univoco per tracing
}
```

**Ogni nodo:**
1. **classify** → `QueryClassifier.classify()` + log evento
2. **retrieve** → `HybridRetriever.retrieve()` + log evento
3. **rerank** → `Reranker.rerank()` + log evento
4. **build_prompt** → `PromptBuilder.build_prompt()`
5. **generate** → filtra PII, chiama `ResponseGenerator.generate()` + log evento
6. **build_citations** → `CitationBuilder.build()`

**Metodi pubblici:**
- `query(question)` → esecuzione sincrona del grafo
- `astream(question)` → generator asincrono per streaming SSE (non usa LangGraph, esegue i passi manualmente per avere più controllo sullo streaming)

**Perché LangGraph?**
- Pipeline chiara e dichiarativa
- Facile da estendere (aggiungere nodi, cambiare ordine)
- Ogni nodo è testabile isolatamente
- Supporto nativo per tracing e monitoring

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
- Eventi intermedi con dati
- Durata in millisecondi

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
│     → top 5 risultati con score > 0.5                                            │
│                                                                                  │
│  5. RERANK (reranker.py)                                                         │
│     → cross-encoder valuta coppie (query, documento)                            │
│     → riordina per pertinenza → mantiene top 3                                  │
│                                                                                  │
│  6. BUILD PROMPT (prompt_builder.py)                                             │
│     → costruisce system prompt con i 3 documenti come contesto                  │
│     → formato: [Documento 1 - titolo] \n Fonte: URL \n contenuto...             │
│                                                                                  │
│  7. GENERATE (llm_client.py + response_generator.py)                            │
│     → filtra PII dal prompt                                                      │
│     → invia a Llama 3.2 via LM Studio (localhost:1234)                          │
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
| Dimensione embedding | 384 | MiniLM L6 - bilancia accuracy/velocità |
| Similarità | Coseno | Standard per embedding normalizzati |
| chunk_size | 512 | Ideale per MiniLM, cattura paragrafi |
| chunk_overlap | 64 (12.5%) | Evita tagli netti nel testo |
| top_k retrieval | 5 | Abbastanza contesto senza eccedere |
| top_k reranker | 3 | Solo i più pertinenti al LLM |
| score_threshold | 0.5 | Filtra rumore |
| Temperature LLM | 0.2 | Risposte fattuali e precise |
| Max pagine crawl | 500 | Copertura ragionevole del sito CNI |
| Profondità crawl | 3 | Homepage → sezioni → sottosezioni |
