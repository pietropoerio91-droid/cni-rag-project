# Indice Tesi — Architettura RAG per il Consiglio Nazionale degli Ingegneri

**Autore:** Pietro Poerio
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`
**Ultimo aggiornamento indice:** 9 settembre 2026

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

> **Risposta raggiunta (annotazione umana chiusa il 3 settembre).** Accuratezza
> **43%** su 30 domande. L'errore residuo si concentra **a monte** del
> generatore: retrieval 47% contro generazione 7%, rapporto 7 a 1. Il vincolo
> hardware si manifesta quindi soprattutto nelle scelte che condizionano il
> recupero, non nella capacità del modello generativo — che, con fedeltà media
> 4,70/5, quasi non allucina. Il capitolo 7 deve tenere distinto ciò che è
> vincolo hardware (embedding a 384 dimensioni, finestra di segmentazione,
> generatore 3B) da ciò che è limite di configurazione (copertura del crawling,
> filtro di categoria), che hardware non è.

---

## Numeri di riferimento del corpus

Da usare in modo coerente in tutta la tesi. **Non accostare mai il conteggio
dei documenti pre-purge a quello dei chunk post-purge.**

| Grandezza | Pre-pulizia | **Post-pulizia (da citare)** |
|---|---:|---:|
| Documenti | 5.890 acquisiti dal crawler | **4.144** (dopo purge `/en/`) |
| Chunk | 17.145 | **13.784** (dopo purge dei duplicati inglesi, 27/08) |

Run di riferimento: `FINAL_V2`, `results/2026-08-28/eval_14-12-22.json`.

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
4.3 Crawling del sito cni.it — 5.890 documenti acquisiti dal crawler, ridotti a 4.144 dopo il purge delle pagine `/en/` (§4.4). **Il perimetro di raccolta e i suoi limiti**: `included_paths` = `/media-ing`, `/cni`, `/temi`, `/contatti`, `/servizi`
4.4 Filtraggio, pulizia e controllo qualità — include il purge dei chunk inglesi del 27/08 (17.145 → 13.784 chunk, §11.6 di `SISTEMA.md`)
4.5 Chunking, embedding e indicizzazione — 13.784 chunk indicizzati oggi, 384 dimensioni, HNSW, distanza coseno
4.6 La pipeline RAG in LangGraph — 9 nodi, 3 archi condizionali
4.7 API REST, streaming SSE e frontend Angular
4.8 Integrazione con Ollama e gestione degli errori

> La 4.1 rende esplicito il vincolo hardware **prima** di descrivere le
> scelte, così ogni decisione successiva appare come conseguenza e non come
> preferenza arbitraria. Sostituisce il confronto fra due macchine previsto
> nella versione precedente.

> **Nuovo in 4.3 (verificato il 09/09).** Il filtro per prefisso su `/cni`
> **non** cattura `/area-cni/`: il gruppo `cni` vi è preceduto da un trattino,
> e in `https://www.cni.it/area-cni/…` la sequenza `/cni` non compare mai —
> né con `startswith` né con matching per sottostringa. Restano quindi fuori
> perimetro **212 pagine**: 106 schede di Ordini provinciali
> (`/area-cni/13-…`) e 106 di Consigli di disciplina (`/area-cni/14-…`), con
> presidente, indirizzo, PEC, codice fiscale e composizione del consiglio di
> ciascun ente. Le pagine indice corrispondenti — `/cni/ordini-provinciali`,
> `/cni/consigli-di-disciplina` — sono nel perimetro e nel corpus, ma sono
> tabelle di soli link (~2.100 caratteri, quasi tutti menu e banner cookie).
> Verificato che quei dati non sono replicati in nessuna pagina interna al
> perimetro. Da presentare come limite del **filtraggio per prefisso applicato
> a una gerarchia di URL che non riflette la gerarchia informativa**, non come
> svista di configurazione: il sito colloca il contenuto figlio su una radice
> sorella.

---

### Capitolo 5 — Metodologia della valutazione ⬜

*Capitolo nuovo. Nella versione precedente dell'indice non esisteva: i
risultati venivano presentati senza mai stabilire perché fossero credibili.*

5.1 Il golden dataset — costruzione, criteri, `reference_answer` ancorate al corpus reale, `expected_sources` verificabili, stratificazione per categoria
5.2 Metriche di retrieval — definizioni adottate (Hit@k, Recall@k, Precision@k, MRR, nDCG@k) e valutazione su due stadi: candidati del retriever e contesto effettivamente ricevuto dal generatore
5.3 **Insidie metodologiche e come sono state evitate** — la ground truth circolare, il recall non troncato, l'asimmetria nel criterio di rilevanza, il matching per sottostringa e i criteri lessicali. Casi reali riscontrati e corretti in questo lavoro
5.4 LLM-as-judge — impianto, prompt, bias di self-preference, criteri di scelta del modello giudice
5.5 **Validazione dello strumento di misura** — annotazione umana in cieco, accordo giudice-umano (kappa pesato, α di Krippendorff, MAE, within-1). Nessun punteggio del giudice viene riportato senza questa validazione
5.6 Impianto statistico — intervalli di confidenza (bootstrap, Wilson), test appaiati (Wilcoxon signed-rank, McNemar esatto), dimensione dell'effetto (δ di Cliff)
5.7 Protocollo sperimentale e riproducibilità — snapshot della configurazione per ogni run, semi fissati, persistenza dei risultati

> La 5.3 trasforma gli errori commessi durante lo sviluppo in contenuto
> scientifico. Una metrica sbagliata individuata e corretta, documentata con
> l'effetto quantificato sui risultati, vale più di una metrica corretta
> presentata senza storia.

> **Da aggiungere in 5.3 — due difetti trovati durante la revisione
> dell'annotazione (03/09).**
> **(a) `expected_sources` con matching per sottostringa e pattern troppo
> corti.** Q15 attende `whistleblowing` e l'URL di un PDF matcha, dando
> `Hit@1 = 1` e `MRR = 1` su un documento che, verificato riga per riga, non
> contiene la risposta. Altri pattern deboli: `urp` (3 caratteri), `euring`
> (6), `contatti` (8), `convenzioni` (11). **Hit@k è sistematicamente
> gonfiato.**
> **(b) `must_contain` promuove le non-risposte.** In Q09 e Q29 il termine
> richiesto compare nel testo del rifiuto, perché la risposta ripete le parole
> della domanda. Rispetto alla correttezza umana: 2 falsi positivi (Q09, Q23)
> e 2 falsi negativi (Q07, Q14). Il 50% del criterio lessicale e il 43%
> umano non coincidono perché la metrica è buona, ma perché **gli errori si
> compensano**.
> Conseguenza operativa: estendere `benchmarks/valida_dataset.py` con
> lunghezza minima del pattern, verifica che la fonte attesa contenga davvero
> i termini di `must_contain`, e controllo che una domanda «chi» abbia un nome
> nel riferimento.

> **Da specificare in 5.5 — che cosa era mascherato.** Scrivere «annotazione
> in cieco» senza dire rispetto a che cosa è insufficiente, ed è la prima
> domanda che un revisore pone. Verificare gli endpoint `/evaluation/*` e
> dichiarare quali informazioni non erano visibili al momento del voto
> (punteggi del giudice automatico, esito del `must_contain`) e quali sì
> (verosimilmente la `reference_answer`, necessaria per giudicare la
> correttezza). Formulazione tipo: «annotazione in cieco rispetto ai punteggi
> automatici, con la risposta di riferimento visibile».
> Motivo metodologico: il kappa misura l'accordo fra due valutatori
> **indipendenti**; se il voto umano fosse stato ancorato a quello del
> giudice, l'accordo sarebbe in parte artificiale.

---

### Capitolo 6 — Risultati ⬜

6.1 Accuratezza del sistema — metriche di retrieval e generazione con intervalli di confidenza al 95%; **confronto fra le tre misure di accuratezza**
6.2 Ablation sul retrieval — top_k, dimensione dei chunk, filtro di categoria. Esperimenti a basso costo: non richiedono generazione
6.3 Effetto del reranking — confronto appaiato pre/post, scelta del modello cross-encoder, analisi della varianza fra domande
6.4 **Decomposizione dell'errore per stadio** — tassonomia dei modi di fallimento (assenza dal corpus, mancato recupero, scarto in reranking, errore in generazione, allucinazione) e distribuzione osservata
6.5 **Il limite del generatore** — test a contesto oracolo: fornendo al modello il documento corretto, quanta parte dell'errore residuo permane
6.6 Costo computazionale — latenza e occupazione di memoria come assi del trade-off qualità/risorse
6.7 Sintesi — risposta alla domanda di ricerca

> **Dati per 6.1 — le tre misure divergono** (30 domande, run `FINAL_V2`,
> annotazione 2–3 settembre):
>
> | Metodo | Corrette su 30 | |
> |---|---:|---:|
> | Annotazione umana | 13 | **43%** |
> | `must_contain` lessicale | 15 | 50% |
> | Giudice `qwen2.5:3b` | 7 | 23% |
>
> Correttezza media 2,34 (umana) contro 1,38 (giudice). Accordo per asse:
> pertinenza kappa +0,770 (media umana 2,50 · giudice 2,77), correttezza
> +0,674 (2,34 · 1,38), fedeltà **−0,019** (4,70 · 3,10).
> Il kappa sulla fedeltà **non è interpretabile** e va riportato come tale,
> non come «disaccordo fra annotatori»: la distribuzione umana è quasi
> degenere (28 voti su 30 pari a 5) e per costruzione azzera il kappa.
> Che la fedeltà umana sia quasi sempre massima **è un risultato**: il sistema
> quasi non allucina, fallisce a monte.
> In tesi l'accuratezza da riportare è quella umana; il giudice va presentato
> come misura **non validata**, e la differenza fra i due come risultato
> metodologico autonomo sull'affidabilità dei giudici LLM di piccola taglia.

> **Dati per 6.4 — decomposizione osservata:**
>
> | Stadio | n | % |
> |---|---:|---:|
> | `retrieval_miss` | 14 | **47%** |
> | `ok` | 13 | 43% |
> | `generation_miss` | 2 | **7%** |
> | `reranker_drop` | 1 | 3% |
>
> **Rapporto 7 a 1** fra errore a monte del generatore (retrieval + reranker
> = 50%) ed errore di generazione (7%). Con il giudice automatico la stessa
> tabella dava `ok` 23% e `generation_miss` 20%: la quota attribuita al
> generatore **si divide per tre** quando si usa l'annotazione umana.
>
> **Garanzia di riproducibilità da dichiarare**: la classificazione manuale
> coincide **30 su 30, zero discordanze**, con quella ricalcolata
> meccanicamente dai rank del run più la correttezza. La codifica degli stadi
> non dipende dal giudizio soggettivo.
>
> Casi singoli da citare: Q06 e Q29 sono astensioni **ingiustificate** — fonte
> corretta nel contesto a rank 1 e rank 2, e il modello dichiara di non avere
> l'informazione. Sono i due `generation_miss`, cioè l'intero 7%. Q09 è
> l'unico `reranker_drop`: fonte a rank 17 fra i candidati, esclusa dal
> reranker.

> **Ridimensionamento di 6.5.** Il test a contesto oracolo era stato concepito
> per *isolare* il limite del generatore per esclusione. L'annotazione umana
> lo ha già quantificato al 7%: l'oracolo ora **conferma un valore misurato,
> non lo scopre**. Va presentato come verifica indipendente di un risultato
> già ottenuto — il che è comunque un rafforzamento, ma non è più il
> passaggio su cui poggia la conclusione.

---

### Capitolo 7 — Discussione ⬜

7.1 Interpretazione dei risultati rispetto alla domanda di ricerca
7.2 **Il retrieval denso e il contenuto schematico** — un unico meccanismo dietro tre fallimenti distinti
7.3 Minacce alla validità — dimensione del golden dataset, dipendenza dal giudice, rappresentatività delle domande, generalizzabilità ad altri corpora, **regressione da filtro di categoria**
7.4 Limiti dichiarati del lavoro

> **7.2 — la sezione nuova.** Tre fallimenti che sembravano scollegati hanno
> lo stesso meccanismo: il retrieval denso fatica sul contenuto **schematico**
> — tabelle, anagrafiche, elenchi — e riesce sulla prosa.
> - `/cni/consiglio` scrive «Angelo Domenico Perrini Presidente», mai «il
>   presidente del CNI è…». Interrogato con «Chi è il presidente del CNI?»,
>   un embedding di frasi trova più affini i comunicati stampa in prosa che
>   nominano il presidente uscente (Q01).
> - `/cni/ordini-provinciali` è una tabella di soli nomi di provincia che
>   fanno da link: semanticamente inerte (Q22).
> - Tre dei cinque documenti recuperati per Q01 sono pagine di elenco
>   paginate.
>
> È l'argomento empirico più solido a favore dell'ibrido BM25 (§8.1), e
> trasforma tre difetti isolati in un risultato unico. Da quantificare prima
> di scriverlo: quanti chunk del corpus sono pagine di elenco (URL con
> `?start=` o pagine indice).

> **Da aggiungere in 7.3 — la regressione da filtro di categoria.** Q01 e Q07
> erano **corrette** in FULL1 (24/08, filtro attivo, fonte a rank 8 e rank 19)
> e **sbagliate** in FINAL_V2 (28/08, filtro disattivato: fonte mai fra i
> candidati). Entrambe riguardano pagine istituzionali sotto `/cni`.
> L'ablation del 27/08 misurava la **media**, non la stratificazione per
> categoria: disattivare il filtro ha alzato Hit@5 complessivo e perso le
> domande istituzionali. È una minaccia alla validità delle ablation stesse,
> e l'indicazione operativa che ne discende non è «filtro sì/no» ma **boost
> morbido di categoria** (§8.7).
>
> Resta da verificare se il pattern regge sulle altre domande di categoria
> `organi` e `formazione`. Se regge, è un risultato in più.

> **Da tenere presente in 7.1 e 7.4 — la distinzione che regge la conclusione.**
> Il 47% di `retrieval_miss` va scomposto fra ciò che è **vincolo hardware**
> (embedding a 384 dimensioni, finestra di segmentazione a 128 token,
> generatore 3B — tutte scelte imposte dagli 8 GB) e ciò che è **limite di
> configurazione** (perimetro del crawling, filtro di categoria), che hardware
> non è. Senza questa distinzione la risposta alla domanda di ricerca
> attribuisce all'hardware un errore che in parte non gli appartiene.

---

### Capitolo 8 — Sviluppi futuri ⬜

8.1 Hybrid search — fusione di ricerca sparsa (BM25) e densa con Reciprocal Rank Fusion. *Attualmente non implementata: il sistema impiega ricerca densa con filtro di categoria.* Giustificazione empirica in §7.2
8.2 Supporto avanzato ai documenti PDF (delibere, circolari)
8.3 Query multi-hop e domande composte
8.4 Feedback degli utenti per il miglioramento continuo
8.5 Esecuzione su GPU e quantizzazione — modelli oltre i 3B
8.6 **Estensione del perimetro di crawling** — ricrawling integrale delle due categorie `/area-cni/13-ordini-provinciali` e `/area-cni/14-consigli-di-disciplina` (212 pagine, §4.3). La versione difendibile è ricrawlare **una classe di pagine definita dalla struttura del sito**, non le pagine che servono a superare una domanda del test, e validare su un insieme di controllo
8.7 **Boost morbido di categoria** al posto del filtro rigido — motivato dalla regressione documentata in §7.3
8.8 **Estensione del golden dataset** — con n=30 la potenza statistica è ~5%: servirebbero circa 500 domande per l'80%. È il primo intervento in ordine di importanza per rendere significativi i confronti fra configurazioni

> Le sezioni 8.6–8.8 sono le uniche sostenute da una misura diretta e da una
> stima del costo. Vanno presentate come diagnosi con rimedio quantificato,
> non come lista di buoni propositi.

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

⚠️ **Da riverificare in `CONCLUSIONI_TESI.md`** alla luce degli aggiornamenti
del 9 settembre: i conteggi del corpus (4.144 documenti, non 5.890), la
diagnosi di Q01 (ranking, non `corpus_miss`) e la quota attribuita al
generatore (7%, non 20%).

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

## Q01 — il caso guida, e la diagnosi corretta tre volte

Da raccontare in §7.2 **compresi gli errori diagnostici**: mostra perché la
decomposizione dell'errore richiede prove dirette e non inferenze dal
comportamento del sistema.

**Domanda**: «Chi è il presidente del CNI?» · **Riferimento**: Angelo Domenico
Perrini · **Risposta in FINAL_V2**: «Il presidente del CNI è Armando
Zambrano» (presidente fino al 2022).

1. Il contesto recuperato contiene 5 documenti 2013–2015, di cui 3 pagine di
   elenco paginate, che dicono «presidente del CNI» riferito al predecessore.
2. Interrogando il sistema con il nome dentro la domanda si ottiene la
   risposta corretta. *Interpretazione poi ritirata*: non era una prova di
   recupero, era il modello che **accetta la premessa** contenuta nella
   domanda — un'affermazione non supportata, stadio *e*. Una query che
   contiene la risposta attesa **verifica**, non **recupera**.
3. Ispezione diretta di ~10 documenti (01/09): nessuno afferma che Perrini è
   presidente. → ipotesi `corpus_miss`, stadio *a*.
4. **Verifica sul sito (09/09): ipotesi scartata.** `/cni/consiglio` è
   **dentro** `included_paths` e il suo HTML grezzo contiene «Angelo Domenico
   Perrini Presidente» con biografia — 12.796 caratteri estraibili contro
   1.732 visibili, perché le schede dei consiglieri sono in una fisarmonica
   chiusa che non ostacola un crawler senza JavaScript.

**Conclusione**: Q01 è un fallimento di **ranking, stadio *b***, non di
copertura. Prova indipendente già agli atti: in FULL1 la fonte era a **rank 8**
e la risposta era corretta — se era a rank 8, era nell'indice. La causa
prossima è la disattivazione del filtro di categoria (§7.3); il meccanismo di
fondo è la fragilità del retrieval denso sul contenuto schematico (§7.2).

**Cautele registrate**: non riformulare le domande del golden dataset in
versioni che il sistema supera, e non eliminare Q01 dal dataset.

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

### Aggiornamenti del 9 settembre 2026

| Modifica | Motivo |
|---|---|
| Aggiunta la tabella «Numeri di riferimento del corpus» | Rischio concreto di accostare 5.890 documenti (pre-purge) a 13.784 chunk (post-purge): coppia incoerente, già comparsa in una bozza dell'abstract |
| Inseriti i risultati definitivi in 6.1 e 6.4 | L'annotazione umana si è chiusa il 3 settembre: l'indice riportava ancora le sezioni senza i numeri |
| Ridimensionato il 6.5 (test oracolo) | L'annotazione ha già quantificato il limite del generatore al 7%: l'oracolo conferma, non scopre |
| Nuova sezione 7.2 sul contenuto schematico; ex 7.2 e 7.3 slittate a 7.3 e 7.4 | Q01, Q22 e le pagine di elenco hanno un unico meccanismo: tre difetti isolati diventano un risultato |
| Aggiunta la regressione da filtro di categoria in 7.3 | Q01 e Q07 corrette in FULL1 e sbagliate in FINAL_V2: minaccia alla validità delle ablation, che misuravano la media e non la stratificazione |
| Documentato in 4.3 il limite di perimetro su `/area-cni/` | 212 pagine territoriali fuori corpus per una regola di prefisso; verificato navigando il sito, non dedotto dal comportamento del sistema |
| Aggiunte 8.6, 8.7, 8.8 | Sono gli unici sviluppi futuri sostenuti da una misura diretta e da una stima del costo |
| Aggiunti in 5.3 i difetti di `expected_sources` e `must_contain` | Trovati durante la revisione dell'annotazione: Hit@k gonfiato, non-risposte promosse |
| Aggiunta la richiesta di esplicitare il mascheramento in 5.5 | «In cieco» senza dire rispetto a che cosa è la prima obiezione che un revisore solleva |
| Aggiunta la sezione «Q01 — il caso guida» | La diagnosi è stata corretta tre volte; il percorso è materiale di tesi, non un imbarazzo da nascondere |
