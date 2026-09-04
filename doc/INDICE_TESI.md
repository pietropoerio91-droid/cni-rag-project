# Indice Tesi — Architettura RAG per il Consiglio Nazionale degli Ingegneri

**Autore:** Pietro Poerio
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`
**Ultimo aggiornamento indice:** 4 settembre 2026

---

## Domanda di ricerca

> **Con quale accuratezza un sistema RAG interamente locale risponde a domande
> sui dati pubblici del Consiglio Nazionale degli Ingegneri, e quanta parte
> dell'errore residuo è imputabile ai vincoli hardware dell'esecuzione in
> locale?**

Due risultati distinti: **quanto è accurato** il sistema, e **perché non lo è
di più**. Il secondo è ciò che distingue una tesi da una relazione tecnica.

Il vincolo di esecuzione locale non è una limitazione da giustificare ma il
presupposto del lavoro: dati della pubblica amministrazione, nessun invio a
servizi terzi, sovranità del dato. La piattaforma è un MacBook Pro 13" del
2017 — Intel Core i5 dual-core, 8 GB di RAM condivisa con la grafica
integrata, nessuna accelerazione GPU disponibile per l'inferenza. È un
vincolo specifico e documentabile, non un generico "hardware consumer".

---

## Struttura

Otto capitoli. I capitoli 1–4 descrivono il sistema; i capitoli 5–7 lo
misurano e ne discutono i limiti. La seconda metà è il contributo.

Legenda stato: ✅ scritto · 🟡 in corso · ⬜ da scrivere

---

### Abstract ✅
### Introduzione ✅

---

### Capitolo 1 — Fondamenti e stato dell'arte ⬜

1.1 Information Retrieval — modelli classici (TF-IDF, BM25), metriche di valutazione
1.2 Rappresentazioni neurali del linguaggio — word embeddings, Transformer, sentence-transformers
1.3 Modelli di embedding multilingua — da `all-MiniLM-L6-v2` a `paraphrase-multilingual-MiniLM-L12-v2`
1.4 Large Language Models — architettura, pre-training, limiti; i modelli di piccola taglia (≤3B) e cosa li distingue
1.5 Retrieval-Augmented Generation — nascita, architettura, pattern naive → advanced → modular
1.6 Corrective RAG e Self-RAG — grade documents, query rewriting, autovalutazione
1.7 **La valutazione dei sistemi RAG** — metriche di retrieval, valutazione della generazione, il paradigma LLM-as-judge (RAGAS, MT-Bench), bias noti e loro mitigazione
1.8 **RAG sotto vincoli di risorse** — quantizzazione, modelli compatti, trade-off qualità/memoria/latenza nei sistemi locali
1.9 **Posizionamento del lavoro** — cosa distingue questo sistema rispetto alla letteratura e alle applicazioni esistenti su dati della PA

> Le sezioni 1.7–1.9 sono nuove. La 1.7 fonda metodologicamente il capitolo 5:
> senza di essa la valutazione sembrerebbe improvvisata. La 1.9 è il
> posizionamento nello stato dell'arte, che in una tesi non è opzionale.

---

### Capitolo 2 — Stack tecnologico ⬜

2.1 Panoramica dell'ecosistema e criteri di selezione (vincolo locale, supporto multilingua, footprint di memoria)
2.2 LangChain e LangGraph — orchestrazione di pipeline LLM come grafi di stato
2.3 Qdrant — database vettoriale in locale (SQLite, indice HNSW)
2.4 Sentence-Transformers — embedding multilingua e cross-encoder per il reranking
2.5 **Ollama — esecuzione locale di LLM su CPU.** Su Mac Intel l'accelerazione Metal non è disponibile: l'inferenza è interamente CPU-bound. È la ragione tecnica dei tempi di risposta misurati nel capitolo 6.6
2.6 Acquisizione ed estrazione documentale — httpx, BeautifulSoup, trafilatura, PyMuPDF
2.7 Interfacce — FastAPI con streaming SSE, frontend Angular

> ⚠️ **Correzione rispetto alla versione precedente dell'indice.** La 2.5
> indicava "Metal GPU": è errato su questa piattaforma. Ollama sfrutta Metal
> soltanto su Apple Silicon; su Intel ricade su inferenza CPU-only e la Iris
> Plus 650 non viene impiegata. La versione corretta è anche la più utile,
> perché spiega i tempi osservati.

---

### Capitolo 3 — Architettura del sistema ⬜

3.1 Requisiti e vincoli — privacy, esecuzione locale, limiti hardware
3.2 Architettura generale — diagramma a blocchi
3.3 Modulo *Ingestion* — crawler → filtro dati pubblici → quality check → cleaner → chunker → embedder → indexer
3.4 Modulo *RAG (LangGraph)* — classify → retrieve → rerank → grade_docs → rewrite_query → build_prompt → generate → self_check → build_citations
3.5 Modulo *Governance* — filtro PII, monitoring, qualità dei contenuti
3.6 Modulo *API* — REST e streaming SSE
3.7 Modulo *Frontend* — chat, dashboard statistiche, **interfaccia di annotazione per la valutazione**, browser Qdrant
3.8 Flusso dati end-to-end

> La 3.7 include ora l'interfaccia di annotazione: non è un accessorio ma lo
> strumento con cui si eseguono la validazione del giudice (5.5) e la codifica
> degli errori (6.4). In quanto tale è parte della metodologia e va descritta.

---

### Capitolo 4 — Implementazione ⬜

4.1 **Piattaforma di esecuzione** — MacBook Pro 13" 2017, Intel Core i5 dual-core 3,1 GHz, 8 GB LPDDR3 condivisi con Intel Iris Plus 650. Implicazioni dirette sulle scelte progettuali: modello generativo da 3B, embedding a 384 dimensioni, assenza di accelerazione hardware
4.2 Configurazione centralizzata (YAML ed environment)
4.3 Crawling del sito cni.it — 5.890 documenti acquisiti dal crawler, ridotti a 4.144 dopo il purge delle pagine `/en/` (§4.4)
4.4 Filtraggio, pulizia e controllo qualità — include il purge dei chunk inglesi del 27/08 (17.145 → 13.784 chunk, §11.6 di `SISTEMA.md`)
4.5 Chunking, embedding e indicizzazione — 13.784 chunk indicizzati oggi, 384 dimensioni, HNSW, distanza coseno
4.6 La pipeline RAG in LangGraph — 9 nodi, 3 archi condizionali
4.7 API REST, streaming SSE e frontend Angular
4.8 Integrazione con Ollama e gestione degli errori

> La 4.1 rende esplicito il vincolo hardware **prima** di descrivere le
> scelte, così ogni decisione successiva appare come conseguenza e non come
> preferenza arbitraria. Sostituisce il confronto fra due macchine previsto
> nella versione precedente.

---

### Capitolo 5 — Metodologia della valutazione ⬜

*Capitolo nuovo. Nella versione precedente dell'indice non esisteva: i
risultati venivano presentati senza mai stabilire perché fossero credibili.*

5.1 Il golden dataset — costruzione, criteri, `reference_answer` ancorate al corpus reale, `expected_sources` verificabili, stratificazione per categoria
5.2 Metriche di retrieval — definizioni adottate (Hit@k, Recall@k, Precision@k, MRR, nDCG@k) e valutazione su due stadi: candidati del retriever e contesto effettivamente ricevuto dal generatore
5.3 **Insidie metodologiche e come sono state evitate** — la ground truth circolare, il recall non troncato, l'asimmetria nel criterio di rilevanza. Casi reali riscontrati e corretti in questo lavoro
5.4 LLM-as-judge — impianto, prompt, bias di self-preference, criteri di scelta del modello giudice
5.5 **Validazione dello strumento di misura** — annotazione umana, accordo giudice-umano (kappa pesato, α di Krippendorff, MAE, within-1). Nessun punteggio del giudice viene riportato senza questa validazione
5.6 Impianto statistico — intervalli di confidenza (bootstrap, Wilson), test appaiati (Wilcoxon signed-rank, McNemar esatto), dimensione dell'effetto (δ di Cliff)
5.7 Protocollo sperimentale e riproducibilità — snapshot della configurazione per ogni run, semi fissati, persistenza dei risultati

> La 5.3 trasforma gli errori commessi durante lo sviluppo in contenuto
> scientifico. Una metrica sbagliata individuata e corretta, documentata con
> l'effetto quantificato sui risultati, vale più di una metrica corretta
> presentata senza storia.

---

### Capitolo 6 — Risultati ⬜

6.1 Accuratezza del sistema — metriche di retrieval e generazione con intervalli di confidenza al 95%
6.2 Ablation sul retrieval — top_k, dimensione dei chunk, filtro di categoria. Esperimenti a basso costo: non richiedono generazione
6.3 Effetto del reranking — confronto appaiato pre/post, scelta del modello cross-encoder, analisi della varianza fra domande
6.4 **Decomposizione dell'errore per stadio** — tassonomia dei modi di fallimento (assenza dal corpus, mancato recupero, scarto in reranking, errore in generazione, allucinazione) e distribuzione osservata
6.5 **Il limite del generatore** — test a contesto oracolo: fornendo al modello il documento corretto, quanta parte dell'errore residuo permane. Quantificazione diretta del costo del vincolo hardware
6.6 Costo computazionale — latenza e occupazione di memoria come assi del trade-off qualità/risorse
6.7 Sintesi — risposta alla domanda di ricerca

> Il 6.5 sostituisce il confronto Windows/Mac della versione precedente:
> risponde alla stessa domanda ("quanto pesa l'hardware?") in modo controllato
> e su una sola macchina. Il confronto fra due macchine era metodologicamente
> debole, perché sistema operativo, RAM e generazione di CPU variavano
> simultaneamente e nessuna differenza sarebbe stata attribuibile a una causa
> specifica.

---

### Capitolo 7 — Discussione ⬜

7.1 Interpretazione dei risultati rispetto alla domanda di ricerca
7.2 Minacce alla validità — dimensione del golden dataset, dipendenza dal giudice, rappresentatività delle domande, generalizzabilità ad altri corpora
7.3 Limiti dichiarati del lavoro

---

### Capitolo 8 — Sviluppi futuri ⬜

8.1 Hybrid search — fusione di ricerca sparsa (BM25) e densa con Reciprocal Rank Fusion. *Attualmente non implementata: il sistema impiega ricerca densa con filtro di categoria*
8.2 Supporto avanzato ai documenti PDF (delibere, circolari)
8.3 Query multi-hop e domande composte
8.4 Feedback degli utenti per il miglioramento continuo
8.5 Esecuzione su GPU e quantizzazione — modelli oltre i 3B

---

### Conclusioni 🟡

Bozza completa in `doc/CONCLUSIONI_TESI.md`: argomentazione e struttura
definitive, dati reali. Tutti e quattro gli esperimenti pianificati sono
stati eseguiti su n=30 — ablation (27/08), valutazione end-to-end `FINAL_V2`
(28/08), test a contesto oracolo (28/08), confronto fra modelli di embedding
(28/08) — e la validazione umana in cieco con accordo giudice-umano (§5.5)
è stata completata il 02-03/09 su tutte le 30 domande. Nessun segnaposto
`[X]` residuo nel documento. 🟡 indica solo che il capitolo va ancora
scritto da Pietro con parole proprie (vedi nota in cima a
`CONCLUSIONI_TESI.md`), non che manchino dati.

---

### Appendici

A — Guida all'installazione e configurazione (macOS)
B — Il golden dataset completo
C — Esempi di query e risposte con citazioni
D — Schema della collezione Qdrant
E — Foglio di validazione umana e calcolo dell'accordo giudice-umano

---

### Bibliografia

---

## Note sulle modifiche rispetto alla versione precedente

| Modifica | Motivo |
|---|---|
| Aggiunta la domanda di ricerca in apertura | L'indice precedente non conteneva, in nessun punto, una domanda a cui rispondere |
| Nuovo capitolo 5 (metodologia della valutazione) | I risultati venivano presentati senza fondarne la credibilità |
| Capitolo dei risultati esteso da 5 a 7 sezioni | Nella versione precedente i risultati erano l'11% delle sottosezioni: struttura da relazione tecnica |
| Aggiunte 1.7, 1.8, 1.9 | Mancavano il fondamento teorico della valutazione e il posizionamento nello stato dell'arte |
| Corretto "Metal GPU" → CPU-only in 2.5 | Errore fattuale: Ollama impiega Metal solo su Apple Silicon |
| Rimosso il confronto Windows/Mac (ex 5.5) | Variabili confuse: sistema operativo, RAM e CPU differivano insieme. Sostituito dal test a contesto oracolo (6.5) |
| Capitoli 2 e 4 consolidati (9→7 e 11→8 sezioni) | Granularità eccessiva sui dettagli implementativi, a scapito dello spazio per i risultati |
| Hybrid search spostata negli sviluppi futuri | Dichiarata nella configurazione ma non implementata nel codice: una discrepanza fra documentazione e sorgenti è un rischio in sede di discussione |
| Aggiunto il capitolo 7 (discussione) | Mancava lo spazio per interpretare i risultati e dichiarare le minacce alla validità |
