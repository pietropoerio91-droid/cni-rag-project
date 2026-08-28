# Conclusioni

> **Nota per la compilazione.** I segnaposto `[X]` vanno sostituiti con i
> valori prodotti dai run finali. Corrispondenza fra segnaposto e comando:
>
> | Segnaposto | Fonte |
> |---|---|
> | Accuratezza di retrieval e generazione (§ Risposta alla domanda di ricerca, §1) | `python benchmarks/run_evaluation.py` sul golden dataset v2 completo (§5.1–5.2) |
> | Quota d'errore imputabile al generatore (§1) | `python benchmarks/oracle_context.py` (§6.5) |
> | Effetto del reranking sull'accuratezza finale (§1) | `python benchmarks/compare_runs.py` pre/post reranking su risposte generate (§6.3) — l'effetto sul solo retrieval è già in `results/report_ablation_2026-08-27.md` (non significativo, n=30) |
> | Accordo giudice-umano (§2) | `python benchmarks/compute_judge_agreement.py` (§5.5) |
> | Decomposizione dell'errore per stadio (§1) | `python benchmarks/ablation_retrieval.py` + analisi manuale dei fallimenti (§6.4) |
> | ~~Effetto del filtro di categoria e del reranker~~ | **fatto** — `results/report_ablation_2026-08-27.md`, n=30, non significativo |
>
> Finché questi run non sono stati eseguiti sul dataset esteso, il capitolo
> resta una bozza strutturale: l'argomentazione è completa, i numeri no.
> Il run `FULL1` (10 domande, 24 agosto) è troppo esiguo per fondarci queste
> affermazioni ed è stato usato solo come prova di funzionamento della
> pipeline di valutazione, non come risultato finale.
>
> **Aggiornamento 28/08**: recuperato `results/ablation_retrieval_2026-08-27_*.json`
> (due run, n=30, golden dataset v2) — vedi `results/report_ablation_2026-08-27.md`.
> Copre solo lo stadio di retrieval/reranking, non la generazione: i segnaposto
> su accuratezza finale e test a contesto oracolo restano da produrre. Il
> risultato dell'ablation è già incorporato in "Limiti", sotto.

---

## Risposta alla domanda di ricerca

Questo lavoro ha posto una domanda in due parti: **con quale accuratezza**
un sistema RAG interamente locale risponde a domande sui dati pubblici del
Consiglio Nazionale degli Ingegneri, e **quanta parte dell'errore residuo**
è imputabile ai vincoli hardware dell'esecuzione in locale.

Sul primo punto, il sistema realizzato — un'architettura RAG completa
(crawling mirato del sito `cni.it`, filtro dei dati pubblici, chunking,
embedding multilingue, indicizzazione vettoriale HNSW, retrieval con
reranking cross-encoder, generazione con auto-verifica e pipeline
orchestrata in LangGraph) — raggiunge un'accuratezza di `[X]%` in Hit@5 sul
retrieval e un punteggio medio di correttezza di `[X]/5` sulla generazione,
con intervallo di confidenza al 95% pari a `[X]` (bootstrap, N=`[X]`
domande del golden dataset v2). Questi valori vanno letti insieme, non
separatamente: il capitolo 6 mostra che gran parte delle risposte errate
non nasce da un fallimento della generazione ma da un fallimento a monte,
nel retrieval o nel reranking — un dato che la sola metrica di correttezza
finale non renderebbe visibile.

Sul secondo punto — la ragione per cui questa tesi include un test a
contesto oracolo (§6.5) — il risultato è che, fornendo al generatore il
documento corretto per costruzione, la correttezza sale a `[X]/5`, contro
`[X]/5` nella pipeline end-to-end. La differenza, pari a `[X]` punti
percentuali, è la stima diretta di quanto pesa la pipeline di retrieval
sull'errore complessivo; il residuo che permane anche a contesto oracolo
(`[X]` punti) è la stima diretta di quanto pesa il modello generativo da 3B
parametri eseguito su CPU, senza accelerazione hardware. Questa
scomposizione — non disponibile confrontando due macchine diverse, per le
ragioni metodologiche discusse in §6.5 — è ciò che permette di rispondere
alla seconda parte della domanda di ricerca con un numero anziché con
un'impressione.

## Il contributo del lavoro

Il contributo di questa tesi non si esaurisce nel sistema funzionante. Tre
elementi vanno oltre l'implementazione:

**Un impianto di valutazione che non si fida delle proprie metriche di
default.** Il benchmark iniziale, basato su keyword matching, giudicava
"corretta" (MRR = 1.0) la risposta alla domanda "Chi è il presidente del
CNI?" nello stesso momento in cui il sistema rispondeva di non saperlo: la
parola "presidente" compariva nel primo chunk recuperato, ma in un
contesto irrilevante. La diagnosi di questo caso — chunk corretto presente
nell'indice ma classificato al rango 20-21 dall'embedding, e scartato dal
reranking perché il cross-encoder in uso era addestrato solo su MS MARCO
inglese — ha portato a due correzioni verificabili (`top_k` 10→25,
sostituzione del reranker con un modello multilingue) e a un principio
metodologico più generale, adottato per il resto del lavoro: **ogni
metrica va validata contro casi noti prima di essere usata per trarre
conclusioni**, ed **in un sistema multilingue ogni componente della
pipeline — non solo l'embedding — va scelto con copertura linguistica
esplicita**. Il capitolo 5 (§5.3) generalizza questo e altri episodi
analoghi (ground truth circolare, recall non troncato) in insidie
metodologiche documentate, non nascoste.

**Un giudice automatico che dichiara i propri limiti invece di
presupporsi affidabile.** Il modello che genera le risposte e il modello
che le valuta sono, per vincolo hardware, lo stesso modello (`qwen2.5:3b`
locale): un rischio noto di bias di self-preference. Anziché ignorarlo, il
lavoro lo misura: l'accordo fra il giudizio del modello e l'annotazione
umana in cieco è `[X]` (kappa pesato), `[X]` (α di Krippendorff), con
errore assoluto medio di `[X]` punti su scala 0-5. Nessun punteggio del
giudice viene riportato nel capitolo dei risultati senza questa
validazione a monte.

**Una scomposizione causale dell'errore, non solo una sua misura.** Sapere
che il sistema sbaglia `[X]%` delle volte è meno utile di sapere *dove*
sbaglia: assenza del dato dal corpus, mancato recupero, scarto in fase di
reranking, o errore proprio della generazione (§6.4). Questa tassonomia,
insieme al test a contesto oracolo, è ciò che permette di distinguere un
limite risolvibile con ingegneria (retrieval, reranking) da un limite
strutturale del vincolo hardware (dimensione del modello generativo).

## Limiti

I limiti del lavoro sono discussi in dettaglio nel capitolo 7; qui vale la
pena richiamarne la gerarchia. Il più rilevante è la dimensione del golden
dataset (§5.1): un impianto statistico accurato non compensa un campione
piccolo, ed è la ragione per cui ogni intervallo di confidenza in questa
tesi va letto con la sua ampiezza, non solo con il suo punto centrale.
Non è un'affermazione astratta: l'ablation study sul retrieval (n=30,
§6.2 — due esecuzioni indipendenti del 27 agosto, riportate per intero in
`results/report_ablation_2026-08-27.md`) mostra un Hit@5 più alto senza
filtro di categoria (40,0%) che con filtro (33,3%–36,7% a seconda della
run), coerente con la decisione presa in configurazione — ma con
intervalli di confidenza al 95% ampiamente sovrapposti e nessuna
differenza, su nessuna metrica, che raggiunga la significatività
statistica (tutte p > 0,05, effetto sempre "trascurabile" per il delta di
Cliff). La decisione di disattivare il filtro resta comunque motivata,
ma dall'argomento strutturale — le sei categorie che il classificatore
non può produrre contengono il 75,8% dei chunk dell'indice — non dalla
significatività di questo esperimento. È l'evidenza diretta che con
n=30 il sistema di valutazione non ha la potenza per distinguere
configurazioni con differenze di questa entità, e che estendere il
golden dataset non è un rifinimento ma una precondizione per conclusioni
quantitative difendibili.

Il secondo limite è la dipendenza dal giudice automatico, mitigata ma non
eliminata dalla validazione umana su un sottoinsieme. Il terzo è la
portata dei risultati: un sistema validato su un solo corpus (i dati
pubblici del CNI) e su una sola piattaforma hardware non generalizza
automaticamente ad altri enti o ad altre configurazioni.

Un limite dichiarato per scelta, non per vincolo, è l'assenza di ricerca
ibrida (BM25 + densa): la configurazione la prevede ma il retriever
implementato usa solo ricerca densa con filtro di categoria. È collocata
fra gli sviluppi futuri (§8.1) invece che presentata come parte del
sistema, per evitare la discrepanza fra documentazione e sorgenti che nella
versione precedente dell'indice della tesi era presente.

## Chiusura

Il vincolo di esecuzione locale, posto come premessa del lavoro e non come
sua giustificazione a posteriori, si è rivelato produttivo proprio perché
costringe a misurare — non solo ad affermare — quanto costa in accuratezza
la sovranità del dato quando l'alternativa (inviare dati della pubblica
amministrazione a un servizio terzo) non è percorribile. Il test a
contesto oracolo è la risposta diretta a questa domanda: `[X]` punti di
correttezza sono il prezzo pagato al modello da 3B parametri su CPU, non
all'architettura RAG in sé, che a parità di contesto corretto si comporta
in modo `[X]`. È su questa distinzione — fra ciò che l'architettura può
fare e ciò che l'hardware disponibile le permette di fare — che si fonda
la risposta finale alla domanda di ricerca.
