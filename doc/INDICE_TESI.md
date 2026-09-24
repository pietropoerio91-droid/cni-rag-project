# Indice Tesi — Architettura RAG per il Consiglio Nazionale degli Ingegneri

**Autore:** Pietro Poerio
**Repository:** `https://github.com/pietropoerio91-droid/cni-rag-project`
**Ultimo aggiornamento indice:** 9 settembre 2026 — *struttura portata da otto a sei capitoli*

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
> 4,70/5, quasi non allucina. Il capitolo 5 deve tenere distinto ciò che è
> vincolo hardware (embedding a 384 dimensioni, finestra di segmentazione,
> generatore 3B) da ciò che è limite di configurazione (copertura del crawling,
> filtro di categoria), che hardware non è.

> **⚠ Aggiornamento 22 settembre — intervento sul recupero applicato, non più
> solo diagnosticato.** Il paragrafo sopra descrive il sistema *congelato*
> (`FINAL_V2`), che resta il punto di partenza della tesi. Dopo la diagnosi è
> stato implementato e misurato il recupero ibrido (denso + BM25, §6.2):
> **accuratezza umana 63,3%** su 30 domande (19/30, +20 punti, Wilcoxon su
> correttezza continua p=0,0085). Lo stadio dell'errore si sposta di
> conseguenza: `retrieval_miss` 47%→7%, `generation_miss` 7%→27% — **il collo
> di bottiglia passa dal recupero al generatore**. Questo cambia la risposta
> alla seconda metà della domanda di ricerca: una parte maggiore dell'errore
> residuo attuale è ora imputabile al generatore da 3B (vincolo hardware
> diretto) piuttosto che alla configurazione del recupero. Run di riferimento:
> `FINAL_V3_DEFINITIVO`, `results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json`;
> tabelle pronte in `results/2026-09-22/RIEPILOGO_FINAL_V3.md`. **Da
> dichiarare**: la combinazione (embedding e5 + BM25 nativo + reranker
> invariato) è stata scelta per un motivo di progetto — eliminare il
> troncamento del testo in fase di embedding, §5.2 — non su una soglia
> numerica; il giudice automatico resta non validato (kappa medio 0,540,
> come per `FINAL_V2`), l'accuratezza da citare è quella umana.

---

## Numeri di riferimento del corpus

Da usare in modo coerente in tutta la tesi. **Non accostare mai il conteggio
dei documenti pre-purge a quello dei chunk post-purge.**

| Grandezza | Pre-pulizia | **Post-pulizia (da citare)** |
|---|---:|---:|
| Documenti | 5.890 acquisiti dal crawler | **4.144** (dopo purge `/en/`) |
| Chunk | 17.145 | **13.784** (dopo purge dei duplicati inglesi, 27/08) |

Run di riferimento: `FINAL_V2`, `results/2026-08-28/eval_14-12-22.json`
(sistema congelato) e `FINAL_V3_DEFINITIVO`,
`results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json` (dopo il recupero ibrido,
§6.2) — **stesso corpus, stessi 4.144 documenti e 13.784 chunk**: nessuna
ingestion è stata rilanciata fra i due run, cambia solo il sistema di
recupero.

---

## Struttura

**Sei capitoli.** I capitoli 1–2 descrivono il sistema; i capitoli 3–5 lo
misurano e ne discutono i limiti; il capitolo 6 conclude. Due capitoli che
descrivono contro tre che misurano: la forma dell'indice dichiara che si
tratta di una tesi sperimentale.

Legenda stato: ✅ scritto · 🟡 in corso · ⬜ da scrivere

---

### Abstract ✅
### Introduzione ✅

> Il paragrafo finale dell'introduzione va allineato ai sei capitoli:
> «La tesi è strutturata come segue: nel primo capitolo vengono descritti i
> fondamenti teorici e lo stato dell'arte, nel secondo l'architettura e
> l'implementazione del sistema. Il terzo capitolo presenta la metodologia di
> valutazione, il quarto i risultati sperimentali e il quinto ne discute le
> implicazioni. Il sesto conclude con le osservazioni finali e i possibili
> sviluppi futuri.»

---

### Capitolo 1 — Fondamenti e stato dell'arte ⬜

1.1 Information Retrieval
1.2 Rappresentazioni neurali del linguaggio — word embeddings, Transformer, sentence-transformers
1.3 Modelli di embedding multilingua — da `all-MiniLM-L6-v2` a `paraphrase-multilingual-MiniLM-L12-v2`
1.4 Large Language Models — architettura, pre-training, limiti; i modelli di piccola taglia (≤3B) e cosa li distingue
1.5 Retrieval-Augmented Generation — nascita, architettura, pattern naive → advanced → modular
1.6 Corrective RAG e Self-RAG — grade documents, query rewriting, autovalutazione
1.7 **La valutazione dei sistemi RAG** — metriche di retrieval, valutazione della generazione, il paradigma LLM-as-judge (RAGAS, MT-Bench), bias noti e loro mitigazione
1.8 **RAG sotto vincoli di risorse** — quantizzazione, modelli compatti, trade-off qualità/memoria/latenza nei sistemi locali
1.9 **Posizionamento del lavoro** — cosa distingue questo sistema rispetto alla letteratura e alle applicazioni esistenti su dati della PA

> Le sezioni 1.7–1.9 sono le più importanti del capitolo. La 1.7 fonda
> metodologicamente il capitolo 3: senza di essa la valutazione sembrerebbe
> improvvisata. La 1.9 è il posizionamento nello stato dell'arte, che in una
> tesi non è opzionale.

---

### Capitolo 2 — Architettura e implementazione del sistema ⬜

*Capitolo unico che assorbe i tre capitoli descrittivi della versione
precedente (stack, architettura, implementazione), da ventitré sezioni a
nove. Progetto e codice sono trattati insieme sezione per sezione, così ogni
scelta implementativa compare accanto alla decisione architetturale che la
motiva.*

2.1 **Requisiti, vincoli e piattaforma di esecuzione** — sovranità del dato e assenza di servizi terzi; MacBook Pro 13" 2017, Intel Core i5 dual-core 3,1 GHz, 8 GB LPDDR3 condivisi con Intel Iris Plus 650. Le implicazioni dirette sulle scelte progettuali: modello generativo da 3B, embedding a 384 dimensioni, nessuna accelerazione hardware
2.2 **Lo stack e i criteri di selezione** — LangChain e LangGraph per l'orchestrazione a grafo di stato, Qdrant come database vettoriale locale (SQLite, indice HNSW), Sentence-Transformers per embedding multilingua e cross-encoder, httpx/BeautifulSoup/trafilatura/PyMuPDF per l'acquisizione, FastAPI con SSE e Angular per le interfacce. Ogni scelta motivata dal footprint di memoria e dal supporto multilingua
2.3 **Ollama e l'inferenza su CPU** — su Mac Intel l'accelerazione Metal non è disponibile: l'inferenza è interamente CPU-bound. È la ragione tecnica dei tempi misurati in §4.6
2.4 **Architettura generale e flusso dati end-to-end** — diagramma a blocchi, i cinque moduli e le loro interfacce
2.5 **Ingestion** — crawler asincrono, perimetro di raccolta e suoi limiti, filtro dei contenuti pubblici, controllo qualità, pulizia, chunking, embedding e indicizzazione. Dal sito ai 4.144 documenti e 13.784 chunk finali
2.6 **La pipeline RAG in LangGraph** — nove nodi (classify → retrieve → rerank → grade_docs → rewrite_query → build_prompt → generate → self_check → build_citations) e tre archi condizionali
2.7 **Governance** — filtro PII, monitoring, qualità dei contenuti
2.8 **API e interfacce** — REST e streaming SSE; frontend Angular con chat, dashboard statistiche, browser Qdrant e **interfaccia di annotazione per la valutazione**
2.9 **Configurazione e gestione degli errori** — configurazione centralizzata YAML ed environment, integrazione con Ollama, comportamento in caso di fallimento

> La 2.1 rende esplicito il vincolo hardware **prima** di descrivere le
> scelte, così ogni decisione successiva appare come conseguenza e non come
> preferenza arbitraria. Sostituisce il confronto fra due macchine previsto
> in una versione precedente dell'indice.

> ⚠️ **Correzione da mantenere in 2.3.** Una versione precedente indicava
> "Metal GPU": è errato su questa piattaforma. Ollama sfrutta Metal soltanto
> su Apple Silicon; su Intel ricade su inferenza CPU-only e la Iris Plus 650
> non viene impiegata. La versione corretta è anche la più utile, perché
> spiega i tempi osservati.

> La 2.8 include l'interfaccia di annotazione: non è un accessorio ma lo
> strumento con cui si eseguono la validazione del giudice (§3.5) e la
> codifica degli errori (§4.4). In quanto tale è parte della metodologia e va
> descritta.

> **Tetto di pagine consigliato per questo capitolo: 25–30.** È il più lungo
> della tesi e quello che Pietro conosce meglio, quindi il più esposto al
> rischio di gonfiarsi a scapito dei capitoli 3–5.

---

### Capitolo 3 — Metodologia della valutazione ⬜

*Capitolo che nella prima versione dell'indice non esisteva: i risultati
venivano presentati senza mai stabilire perché fossero credibili.*

3.1 Il golden dataset — costruzione, criteri, `reference_answer` ancorate al corpus reale, `expected_sources` verificabili, stratificazione per categoria
3.2 Metriche di retrieval — definizioni adottate (Hit@k, Recall@k, Precision@k, MRR, nDCG@k) e valutazione su due stadi: candidati del retriever e contesto effettivamente ricevuto dal generatore
3.3 **Bias e insidie metodologiche della valutazione RAG** — la ground truth circolare, il recall non troncato, l'asimmetria nel criterio di rilevanza, il matching per sottostringa e i criteri lessicali. Casi reali riscontrati e corretti in questo lavoro
3.4 **LLM come generatore e valutatore** — impianto, prompt, bias di self-preference, criteri di scelta del modello giudice
3.5 **Validazione dello strumento di misura** — annotazione umana in cieco, accordo giudice-umano (kappa pesato, α di Krippendorff, MAE, within-1). Nessun punteggio del giudice viene riportato senza questa validazione
3.6 Impianto statistico — intervalli di confidenza (bootstrap, Wilson), test appaiati (Wilcoxon signed-rank, McNemar esatto), dimensione dell'effetto (δ di Cliff)
3.7 Protocollo sperimentale e riproducibilità — snapshot della configurazione per ogni run, semi fissati, persistenza dei risultati

> La 3.3 trasforma gli errori commessi durante lo sviluppo in contenuto
> scientifico. Una metrica sbagliata individuata e corretta, documentata con
> l'effetto quantificato sui risultati, vale più di una metrica corretta
> presentata senza storia.

> **Da aggiungere in 3.3 — due difetti trovati durante la revisione
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
> e 2 falsi negativi (Q07, Q14). Il 50% del criterio lessicale e il 43% umano
> non coincidono perché la metrica è buona, ma perché **gli errori si
> compensano**.
> Conseguenza operativa: estendere `benchmarks/valida_dataset.py` con
> lunghezza minima del pattern, verifica che la fonte attesa contenga davvero
> i termini di `must_contain`, e controllo che una domanda «chi» abbia un nome
> nel riferimento.

> **Da specificare in 3.5 — che cosa era mascherato.** Scrivere «annotazione
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

> **Limite da dichiarare in 3.6.** Con n=30 la potenza statistica è ~5%:
> nessuno dei confronti fra configurazioni raggiunge la significatività
> (p 0,375 / 0,688 / 1,000). Servirebbero circa 500 domande per l'80%. Va
> dichiarato qui, non nascosto nei limiti finali.

---

### Capitolo 4 — Risultati ⬜

4.1 Accuratezza del sistema — metriche di retrieval e generazione con intervalli di confidenza al 95%; **confronto fra le tre misure di accuratezza**
4.2 Ablation sul retrieval — top_k, dimensione dei chunk, filtro di categoria. Esperimenti a basso costo: non richiedono generazione
4.3 Effetto del reranking — confronto appaiato pre/post, scelta del modello cross-encoder, analisi della varianza fra domande
4.4 **Decomposizione dell'errore per stadio** — tassonomia dei modi di fallimento (assenza dal corpus, mancato recupero, scarto in reranking, errore in generazione, allucinazione) e distribuzione osservata
4.5 **Il limite del generatore** — test a contesto oracolo: fornendo al modello il documento corretto, quanta parte dell'errore residuo permane
4.6 Costo computazionale — latenza e occupazione di memoria come assi del trade-off qualità/risorse
4.7 Sintesi dei risultati

> **Dati per 4.1 — le tre misure divergono** (30 domande, run `FINAL_V2`,
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

> **Dati per 4.4 — decomposizione osservata:**
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
> reranker. Q07 ha fedeltà 1 e correttezza 3: risposta costruita su una fonte
> diversa da quella attesa, corretta sul meccanismo e sbagliata sul gestore.

> **Ridimensionamento di 4.5.** Il test a contesto oracolo era stato concepito
> per *isolare* il limite del generatore per esclusione. L'annotazione umana
> lo ha già quantificato al 7%: l'oracolo ora **conferma un valore misurato,
> non lo scopre**. Va presentato come verifica indipendente di un risultato
> già ottenuto — il che è comunque un rafforzamento, ma non è più il passaggio
> su cui poggia la conclusione.

> **Insight su MRR da riportare in 4.3**: quando il documento corretto entra
> nel contesto sta in posizione media 1,4 — il reranker ordina bene, il
> problema è farglielo arrivare.

> **⚠ Dati aggiornati per 4.1 e 4.4 dopo il recupero ibrido** (30 domande,
> run `FINAL_V3_DEFINITIVO`, annotazione umana chiusa il 22 settembre — stessa
> procedura e stessa persona che ha annotato `FINAL_V2`, criteri invariati):
>
> | Metodo | Corrette su 30 | | Δ vs FINAL_V2 |
> |---|---:|---:|---:|
> | Annotazione umana | 19 | **63,3%** | +20,0 punti (p=0,0085 su correttezza continua, Wilcoxon; McNemar sul binario p=0,146, non significativo) |
>
> | Stadio | n | % | Δ vs FINAL_V2 |
> |---|---:|---:|---:|
> | `ok` | 19 | 63% | +20 punti |
> | `retrieval_miss` | 2 | **7%** | −40 punti |
> | `reranker_drop` | 1 | 3% | invariato |
> | `generation_miss` | 8 | **27%** | +20 punti |
>
> **Il rapporto si inverte**: da 7 a 1 a favore dell'errore a monte
> (`FINAL_V2`) a circa 1 a 3 a favore dell'errore di generazione
> (`retrieval_miss`+`reranker_drop` = 10% contro `generation_miss` = 27%).
> Con un recupero migliore, **il generatore da 3B diventa il fattore
> dominante dell'errore residuo** — risposta diretta alla seconda metà della
> domanda di ricerca. Le 9 domande migliorate, le 3 peggiorate e le 18
> invariate rispetto a `FINAL_V2`, con lo stadio di ciascuna, sono nella
> dashboard (`/statistiche` → Qualitative → Confronto per domanda) e in
> `results/annotations_FINAL_V3_DEFINITIVO.json`.
>
> **Da dichiarare**: l'intervento (BM25 ibrido, embedding e5, tutto §6.2) è
> stato scelto guardando gli errori di queste stesse 30 domande — non è una
> generalizzazione provata, è descrittivo. La significatività statistica del
> confronto binario (43,3%→63,3%) non è raggiunta (p=0,146); lo è quella del
> confronto sulla correttezza continua (p=0,0085), una misura più sensibile
> ma meno immediata da presentare. Riportare entrambe, non solo la seconda.

---

### Capitolo 5 — Discussione ⬜

5.1 Interpretazione dei risultati rispetto alla domanda di ricerca
5.2 **Il retrieval denso e il contenuto schematico** — un unico meccanismo dietro tre fallimenti distinti
5.3 Minacce alla validità — dimensione del golden dataset, dipendenza dal giudice, rappresentatività delle domande, generalizzabilità ad altri corpora, **regressione da filtro di categoria**, selezione della configurazione sullo stesso insieme di valutazione
5.4 Limiti dichiarati del lavoro

> **5.2 — la sezione nuova.** Tre fallimenti che sembravano scollegati hanno
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
> È l'argomento empirico più solido a favore dell'ibrido BM25 (§6.2), e
> trasforma tre difetti isolati in un risultato unico. Da quantificare prima
> di scriverlo: quanti chunk del corpus sono pagine di elenco (URL con
> `?start=` o pagine indice).

> **⚠ Confermato il 22/09 — la previsione si è avverata.** Il BM25, aggiunto
> proprio per il contenuto schematico appena descritto, porta l'accuratezza
> umana dal 43,3% al 63,3% (§4.1). Non prova che il meccanismo descritto sia
> l'unica causa — l'intervento cambia insieme embedding e reranker, non un
> parametro alla volta (vedi §5.3, selezione sul set di valutazione) — ma è
> coerente con la diagnosi: BM25 recupera per corrispondenza esatta di
> termini (nomi, codici, sigle), esattamente ciò che il contenuto schematico
> non offre a un embedding di frasi.

> **Da aggiungere in 5.3 — la regressione da filtro di categoria.** Q01 e Q07
> erano **corrette** in FULL1 (24/08, filtro attivo, fonte a rank 8 e rank 19)
> e **sbagliate** in FINAL_V2 (28/08, filtro disattivato: fonte mai fra i
> candidati). Entrambe riguardano pagine istituzionali sotto `/cni`.
> L'ablation del 27/08 misurava la **media**, non la stratificazione per
> categoria: disattivare il filtro ha alzato Hit@5 complessivo e perso le
> domande istituzionali. È una minaccia alla validità delle ablation stesse,
> e l'indicazione operativa che ne discende non è «filtro sì/no» ma **boost
> morbido di categoria** (§6.2).
> Resta da verificare se il pattern regge sulle altre domande di categoria
> `organi` e `formazione`. Se regge, è un risultato in più.

> **Da dichiarare in 5.3 — la selezione sul set di valutazione.** Nove
> configurazioni di ablation sono state provate sulle stesse 30 domande e
> poi si è scelta la migliore: tecnicamente è selezione sul set di test.
> Ciò che rende difendibile la scelta è che aveva una **spiegazione
> meccanicistica misurata prima** (il 75,8% dell'indice irraggiungibile per il
> filtro rigido), non solo un numero migliore. La distinzione va scritta
> esplicitamente — tanto più ora che sappiamo che quella scelta ha causato una
> regressione sulle domande istituzionali.

> **Da tenere presente in 5.1 e 5.4 — la distinzione che regge la conclusione.**
> Il 47% di `retrieval_miss` va scomposto fra ciò che è **vincolo hardware**
> (embedding a 384 dimensioni, finestra di segmentazione a 128 token,
> generatore 3B — tutte scelte imposte dagli 8 GB) e ciò che è **limite di
> configurazione** (perimetro del crawling, filtro di categoria), che hardware
> non è. Senza questa distinzione la risposta alla domanda di ricerca
> attribuisce all'hardware un errore che in parte non gli appartiene.

---

### Capitolo 6 — Conclusioni e sviluppi futuri 🟡

6.1 **Conclusioni** — risposta alla domanda di ricerca e contributi del lavoro
6.2 **Interventi sul recupero** — hybrid search con fusione di ricerca sparsa (BM25) e densa mediante Reciprocal Rank Fusion: **implementata e misurata il 21-22/09** (vedi nota sotto), non più uno sviluppo futuro; boost morbido di categoria in luogo del filtro rigido (§5.3, resta da fare)
6.3 **Estensione della valutazione** — golden dataset portato a circa 500 domande per raggiungere una potenza dell'80%; insieme di controllo indipendente scritto dopo il congelamento della configurazione
6.4 **Estensioni funzionali** — supporto avanzato ai documenti PDF (delibere, circolari), query multi-hop e domande composte, feedback degli utenti per il miglioramento continuo
6.5 **Superamento del vincolo hardware** — esecuzione su GPU e quantizzazione, modelli oltre i 3B

> Le voci di 6.2 e 6.3 sono le uniche sostenute da una misura diretta e da una
> stima del costo. Vanno presentate come diagnosi con rimedio quantificato,
> non come lista di buoni propositi.
>
> **Costo di ogni adozione, da dichiarare**: un run completo da circa 4 ore
> **più 90 giudizi umani da rifare**. È la ragione per cui gli interventi
> identificati non sono stati applicati prima della consegna: adottarli senza
> riannotare avrebbe prodotto numeri nuovi e non validati, cioè peggiori di
> quelli riportati.

> **⚠ 6.2 non è più «da fare»: il costo è stato pagato e i numeri sono validi.**
> Fra il 20 e il 22/09, dopo il congelamento di `FINAL_V2`, sono stati
> eseguiti: (1) BM25 nativo in Qdrant con Reciprocal Rank Fusion lato server
> (vettore sparso, modificatore IDF, un'unica chiamata al database — non una
> somma pesata: le scale coseno/BM25 sono incomparabili); (2) un confronto a
> 6 configurazioni (3 modelli di embedding × con/senza BM25) e a 3 reranker,
> tutti sulle stesse 30 domande; (3) il run end-to-end completo e le 90
> valutazioni umane rifatte da zero, con revisione di 4 annotazioni dopo
> verifica sui dati grezzi. Risultato: accuratezza umana 43,3%→63,3% (§4.1).
> Il boost morbido di categoria (l'altra voce di questo paragrafo) **resta
> da fare** — non è stato toccato.
>
> **Cosa scrivere in 6.2 ora**: non più «ecco cosa si potrebbe provare», ma
> «ecco cosa è stato provato, con quale esito, e quali domande restano
> aperte» — la selezione sul set di valutazione (§5.3), l'assunzione non
> verificata che il reranker scelto su un embedding poi cambiato regga anche
> con quello nuovo (`doc/TEST_RECUPERO_IBRIDO.md`, esperimenti §5 e §8).
> Documentazione completa, un esperimento per sezione: `doc/TEST_RECUPERO_IBRIDO.md`.
>
> **Limiti tecnici di §11.7-§11.10 di `doc/SISTEMA.md`: chiusi il 23/09, non
> più aperti.** Pattern di categoria per la whitelist ampliata, indicizzazione a
> lotti, re-indicizzazione su una collection nuova invece che sulla produzione,
> e scelta della collection attiva dal frontend. Sono correzioni di ingegneria
> successive al run `FINAL_V3`: non cambiano la configurazione congelata né i
> numeri riportati (la collection validata resta `cni_documents_e5_bm25`), e
> valgono dalla prossima indicizzazione. In tesi vanno eventualmente citate
> nel capitolo 2 come robustezza del sistema, non in 6.2 come limiti aperti.

> **Sul 6.1.** Bozza completa in `doc/CONCLUSIONI_TESI.md`: argomentazione e
> struttura definitive, dati reali. Tutti e quattro gli esperimenti pianificati
> sono stati eseguiti su n=30 — ablation (27/08), valutazione end-to-end
> `FINAL_V2` (28/08), test a contesto oracolo (28/08), confronto fra modelli di
> embedding (28/08) — e la validazione umana in cieco (§3.5) è stata completata
> il 02–03/09 su tutte le 30 domande. 🟡 indica solo che il capitolo va ancora
> scritto da Pietro con parole proprie, non che manchino dati.
>
> ✅ **`CONCLUSIONI_TESI.md` aggiornato il 23/09 a `FINAL_V3`** (accuratezza
> umana 63,3%, collo di bottiglia spostato sul generatore, giudice non
> validato nemmeno su V3, test oracolo non rimisurato). Scritto per punti, con
> fonti e cautele: il testo del 6.1 resta da scrivere. La versione precedente,
> tutta su `FINAL_V2`, è in `archivio/`. I punti da riverificare segnalati il
> 9/09 (corpus 4.144 documenti, diagnosi di Q01 per ranking, numerazione dei
> capitoli) sono allineati; la quota del generatore ora è il 27% di V3 (era il
> 7% di V2).

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

Da raccontare in §5.2 **compresi gli errori diagnostici**: mostra perché la
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
   domanda — un'affermazione non supportata. Una query che contiene la
   risposta attesa **verifica**, non **recupera**.
3. Ispezione diretta di ~10 documenti (01/09): nessuno afferma che Perrini è
   presidente. → ipotesi `corpus_miss`.
4. **Verifica sul sito (09/09): ipotesi scartata.** `/cni/consiglio` è
   **dentro** `included_paths` e il suo HTML grezzo contiene «Angelo Domenico
   Perrini Presidente» con biografia — 12.796 caratteri estraibili contro
   1.732 visibili, perché le schede dei consiglieri sono in una fisarmonica
   chiusa che non ostacola un crawler senza JavaScript.

**Conclusione**: Q01 è un fallimento di **ranking**, non di copertura. Prova
indipendente già agli atti: in FULL1 la fonte era a **rank 8** e la risposta
era corretta — se era a rank 8, era nell'indice. La causa prossima è la
disattivazione del filtro di categoria (§5.3); il meccanismo di fondo è la
fragilità del retrieval denso sul contenuto schematico (§5.2).

**Perché è un buon caso da tesi**: i tre assi della griglia divergono al
massimo (risposta fedele, pertinente e sbagliata); mostra che il `must_contain`
non separa il grounding dalla conoscenza parametrica; mostra un errore di
protocollo facile da commettere in valutazione, documentato con la sua
correzione.

**Cautele registrate**: non riformulare le domande del golden dataset in
versioni che il sistema supera, e non eliminare Q01 dal dataset.

---

## Note sulle modifiche

### Revisione strutturale del 9 settembre 2026 — da otto capitoli a sei

| Vecchio | Nuovo |
|---|---|
| 1 Fondamenti e stato dell'arte | 1, invariato |
| 2 Stack tecnologico | assorbito in 2.2 e 2.3 |
| 3 Architettura del sistema | confluito in 2 |
| 4 Implementazione | confluito in 2 |
| 5 Metodologia della valutazione | 3 |
| 6 Risultati | 4 |
| 7 Discussione | 5 |
| 8 Sviluppi futuri + Conclusioni | 6 |

I tre capitoli descrittivi passano da 23 sezioni complessive a 9. Progetto e
implementazione sono trattati insieme sezione per sezione, così ogni scelta di
codice compare accanto alla decisione architetturale che la motiva, invece di
essere descritta due volte a due livelli diversi. Gli sviluppi futuri passano
da 5 voci sparse a 4 gruppi tematici.

**Riferimenti incrociati aggiornati** in tutto il documento. Da controllare a
mano fuori da questo file: `CONCLUSIONI_TESI.md`, `SISTEMA.md`, `README.md` e
il paragrafo finale dell'introduzione.

### Modifiche di contenuto del 9 settembre 2026

| Modifica | Motivo |
|---|---|
| Aggiunta la tabella «Numeri di riferimento del corpus» | Rischio concreto di accostare 5.890 documenti (pre-purge) a 13.784 chunk (post-purge): coppia incoerente, già comparsa in una bozza dell'abstract |
| Inseriti i risultati definitivi in 4.1 e 4.4 | L'annotazione umana si è chiusa il 3 settembre: l'indice riportava ancora le sezioni senza i numeri |
| Ridimensionato il 4.5 (test oracolo) | L'annotazione ha già quantificato il limite del generatore al 7%: l'oracolo conferma, non scopre |
| Nuova sezione 5.2 sul contenuto schematico | Q01, Q22 e le pagine di elenco hanno un unico meccanismo: tre difetti isolati diventano un risultato |
| Aggiunte in 5.3 la regressione da filtro di categoria e la selezione sul set di valutazione | Due minacce alla validità che l'indice non dichiarava |
| Aggiunti in 3.3 i difetti di `expected_sources` e `must_contain` | Trovati durante la revisione dell'annotazione: Hit@k gonfiato, non-risposte promosse |
| Aggiunta la richiesta di esplicitare il mascheramento in 3.5 | «In cieco» senza dire rispetto a che cosa è la prima obiezione che un revisore solleva |
| Dichiarata in 3.6 la potenza statistica | Con n=30 nessun confronto è significativo: va detto nella metodologia, non nascosto nei limiti |
| Aggiunta la sezione «Q01 — il caso guida» | La diagnosi è stata corretta tre volte; il percorso è materiale di tesi, non un imbarazzo da nascondere |

### Modifiche di contenuto del 22 settembre 2026

Proposte da revisionare — nessuna riscrittura del testo esistente, solo
blocchi `>` aggiunti in coda alle sezioni già presenti e una correzione di
fatto in 6.2 (l'unica riga di testo esistente toccata: dichiarava «hybrid
search... non implementata», ora falso).

| Modifica | Motivo |
|---|---|
| Blocco «Aggiornamento 22 settembre» dopo la risposta alla domanda di ricerca | L'accuratezza è salita dal 43% al 63,3% dopo il recupero ibrido: la risposta raggiunta il 3/09 resta valida per `FINAL_V2` ma non è più l'ultimo dato disponibile |
| 6.2 corretta da «non implementata» a «implementata e misurata» | Affermazione di fatto, non di giudizio: lasciarla avrebbe reso l'indice esplicitamente falso rispetto al codice |
| Dati aggiornati in 4.1/4.4 (nuova tabella, non sostituita quella vecchia) | Il rapporto errore-a-monte/errore-di-generazione si inverte (7:1 → circa 1:3): cambia la lettura della domanda di ricerca, non solo un numero |
| Conferma in 5.2 | La sezione prevedeva esplicitamente il BM25 come rimedio al contenuto schematico; l'esito lo conferma — va detto, non lasciato implicito |
| `doc/TEST_RECUPERO_IBRIDO.md` citato come fonte | Un esperimento per sezione (comando, branch, file dei risultati, limiti): dove trovare la prova di ogni numero citato qui |

**Non ancora rivisto in questo passaggio**: 5.3 (selezione sul set di
valutazione — vale ancora, ma ora sono 9+ configurazioni provate, non
9), 5.4, l'abstract, l'introduzione, `CONCLUSIONI_TESI.md`. Il paragrafo
finale dell'introduzione (struttura dei capitoli) non è toccato da questo
lavoro: resta valido.

### Modifiche precedenti (versioni di agosto e 4 settembre)

| Modifica | Motivo |
|---|---|
| Aggiunta la domanda di ricerca in apertura | L'indice iniziale non conteneva, in nessun punto, una domanda a cui rispondere |
| Introdotto il capitolo di metodologia della valutazione | I risultati venivano presentati senza fondarne la credibilità |
| Capitolo dei risultati esteso da 5 a 7 sezioni | I risultati erano l'11% delle sottosezioni: struttura da relazione tecnica |
| Aggiunte 1.7, 1.8, 1.9 | Mancavano il fondamento teorico della valutazione e il posizionamento nello stato dell'arte |
| Corretto "Metal GPU" → CPU-only | Errore fattuale: Ollama impiega Metal solo su Apple Silicon |
| Rimosso il confronto Windows/Mac | Variabili confuse: sistema operativo, RAM e CPU differivano insieme. Sostituito dal test a contesto oracolo |
| Hybrid search spostata negli sviluppi futuri | Dichiarata nella configurazione ma non implementata nel codice: una discrepanza fra documentazione e sorgenti è un rischio in sede di discussione |
| Aggiunto il capitolo di discussione | Mancava lo spazio per interpretare i risultati e dichiarare le minacce alla validità |
