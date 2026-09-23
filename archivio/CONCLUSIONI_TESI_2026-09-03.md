# Conclusioni — MATERIALE DI LAVORO, NON TESTO DA CONSEGNARE

> ⚠️ **Questo file è un appunto tecnico per me (Claude), non una bozza da
> incollare nella tesi.** L'uso di AI concordato per questo progetto copre lo
> sviluppo del sistema (codice, benchmark, fix, esperimenti), non la stesura
> del testo della tesi, che passa per un controllo antiplagio. Il capitolo
> Conclusioni va scritto da Pietro con le proprie parole; questo documento
> serve solo a tenere allineati i dati, la struttura logica e cosa ancora
> manca, cosi' l'aiuto sui numeri e sulla verifica dei fatti resta utile
> senza sconfinare nella stesura.

> **Nota per la compilazione.** I segnaposto `[X]` vanno sostituiti con i
> valori prodotti dai run finali. Corrispondenza fra segnaposto e comando:
>
> | Segnaposto | Fonte |
> |---|---|
> | ~~Accuratezza di retrieval e generazione~~ | **fatto** — `results/report_FINAL_V2.md`, n=30, run `FINAL_V2` del 28/08 |
> | ~~Quota d'errore imputabile al generatore~~ | **fatto** — `results/oracle_context_2026-08-28_14-35.json`: 23,3 punti generatore, 26,7 punti retrieval, n=30, McNemar p=0,115 (non significativo) |
> | Effetto del reranking sull'accuratezza finale (§1) | `python benchmarks/compare_runs.py` pre/post reranking su risposte generate (§6.3) — l'effetto sul solo retrieval è già in `results/report_ablation_2026-08-27.md` (non significativo, n=30) |
> | ~~Accordo giudice-umano (§2)~~ | **fatto** — `results/annotations_FINAL_V2.json`, n=30, 02-03/09: kappa medio 0,475 ("moderato"), pertinenza e correttezza sostanziale (0,770 / 0,674), fedeltà nessun accordo (-0,019) — vedi "Il contributo del lavoro" |
> | Decomposizione dell'errore per stadio (§1) | `python benchmarks/ablation_retrieval.py` + analisi manuale dei fallimenti (§6.4) |
> | ~~Effetto del filtro di categoria e del reranker~~ | **fatto** — `results/report_ablation_2026-08-27.md`, n=30, non significativo |
>
> Finché questi run non sono stati eseguiti sul dataset esteso, il capitolo
> resta una bozza strutturale: l'argomentazione è completa, i numeri no.
> Il run `FULL1` (10 domande, 24 agosto) è troppo esiguo per fondarci queste
> affermazioni ed è stato usato solo come prova di funzionamento della
> pipeline di valutazione, non come risultato finale.
>
> **Aggiornamento 03/09**: annotazione umana in cieco completata su tutte
> le 30 domande di `FINAL_V2` e confrontata col giudice automatico — vedi
> tabella sopra. Con questo, tutti i segnaposto `[X]` del documento sono
> compilati con dati reali; restano solo i due punti a bassa priorità
> (effetto reranking isolato, §1) non necessari per rispondere alla
> domanda di ricerca centrale.

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
orchestrata in LangGraph) — raggiunge un'accuratezza di **40,0% [24,6%,
57,7%]** in Hit@5 sul retrieval (contesto passato al generatore) e un
punteggio medio di correttezza di **1,33/5 [0,73, 1,97]** (mediana 0)
sulla generazione, secondo il giudice automatico, su N=30 domande del
golden dataset v2 (run `FINAL_V2`, 28/08 — dettaglio completo in
`results/report_FINAL_V2.md`). Questo secondo numero va letto con la sua
calibrazione nota (si veda la nota metodologica subito sotto): la
correttezza umana mediata sulle stesse 30 domande è **2,35/5**, quindi il
giudice automatico sottostima sistematicamente di circa un punto — l'
*ordinamento* delle risposte è comunque affidabile (kappa 0,674,
"sostanziale"), solo il livello assoluto no. Questi valori vanno letti
insieme, non separatamente: la decomposizione dell'errore per stadio
(§6.4, metodo automatico su rango pre/post-rerank) mostra che il **57%
delle domande (17/30)** fallisce già al retrieval — la fonte corretta
non entra mai fra i 25 candidati — contro un 20% (6/30) in cui il
contesto era corretto ma la generazione ha comunque sbagliato, e un 3%
(1/30) perso dal reranker. Una seconda decomposizione, indipendente,
fatta dall'annotatore umano in cieco sulle stesse 30 domande
(`results/annotations_FINAL_V2.json`, non un calcolo automatico ma una
lettura diretta di risposta e documenti) converge sullo stesso
collo di bottiglia ma con proporzioni diverse: **46,7% (14/30)
retrieval_miss**, **43,3% (13/30) ok**, 6,7% (2/30) generation_miss, 3,3%
(1/30) reranker_drop. Le due decomposizioni concordano sul fatto
qualitativo — il retrieval è la causa dominante, il reranker quasi
irrilevante — ma non sui numeri: il metodo automatico, basato su soglie
di correttezza e rango, classifica più casi come generation_miss (20%
contro 6,7% umano) e meno come "ok" (20% contro 43,3% umano). È un
disaccordo informativo, non un rumore da ignorare: un giudizio umano
olistico è più indulgente nel decidere se una risposta "ha funzionato"
di quanto lo sia una soglia numerica rigida. Con entrambe le letture, il
collo di bottiglia dominante resta comunque a monte della generazione,
non dentro di essa — un dato che la sola metrica di correttezza finale
non renderebbe visibile.

> Nota metodologica: l'accordo giudice-umano (§5.5, completato il
> 02-03/09 su tutte le 30 domande — `results/annotations_FINAL_V2.json`,
> `results/judge_agreement_2026-09-03.json`) dà un risultato **misto, non
> uniforme fra le tre metriche**: pertinenza (kappa 0,770) e correttezza
> (kappa 0,674) hanno un accordo "sostanziale" e sono quindi riportabili
> con la calibrazione indicata sopra; la **fedeltà** ha un accordo
> sostanzialmente nullo (kappa -0,019, MAE 2,0 punti) e **i suoi
> punteggi automatici non vengono riportati come misura affidabile in
> questo lavoro**. Il kappa medio sulle tre metriche è 0,475
> ("moderato"), sotto la soglia di utilizzabilità dichiarata a monte
> (≥0,61) — coerente con l'ipotesi di partenza di un rischio di
> self-preference bias (giudice e generatore sono lo stesso modello),
> confermata empiricamente almeno per la fedeltà.

Sul secondo punto — la ragione per cui questa tesi include un test a
contesto oracolo (§6.5) — il risultato è che, fornendo al generatore il
documento corretto per costruzione, la quota di risposte corrette
(must-contain) sale a **76,7% [59,1%, 88,2%]**, contro **50,0%** nella
pipeline end-to-end (stessa metrica deterministica, stesse 30 domande —
`results/oracle_context_2026-08-28_14-35.json`). La differenza, **26,7
punti percentuali**, è la stima diretta di quanto pesa la pipeline di
retrieval sull'errore complessivo; il residuo che permane anche a
contesto oracolo, **23,3 punti**, è la stima diretta di quanto pesa il
modello generativo da 3B parametri eseguito su CPU, senza accelerazione
hardware. Il test McNemar sulla differenza appaiata non raggiunge la
significatività a questa numerosità (p=0,115) — coerente con il limite
di potenza statistica già discusso, e un'ulteriore ragione per leggere
questi due numeri come stime con margine, non come valori esatti.
Questa scomposizione — non disponibile confrontando due macchine diverse,
per le ragioni metodologiche discusse in §6.5 — è ciò che permette di
rispondere alla seconda parte della domanda di ricerca con un numero
anziché con un'impressione: **della quota di errore non spiegata dal
contesto oracolo, poco più della metà (23,3 punti su 50,0 mancanti) è
imputabile al vincolo hardware sul generatore; il resto (26,7 punti) è
un limite del retrieval, in linea di principio risolvibile senza cambiare
la piattaforma.**

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
lavoro lo misura, confrontando il giudizio automatico con l'annotazione
umana in cieco sulle stesse 30 domande (`results/annotations_FINAL_V2.json`,
02-03/09/2026). Il risultato non è uniforme fra le tre metriche, ed è
proprio questa non uniformità il dato rilevante: su **pertinenza**
(kappa pesato 0,770, "sostanziale") e **correttezza** (kappa 0,674,
"sostanziale") il giudice concorda con l'annotatore umano in modo
solido (r di Pearson 0,80 e 0,79). Su **fedeltà** l'accordo è invece
sostanzialmente nullo (kappa -0,019, MAE 2,0 punti su scala 0-5): il
giudice assegna in media 3,1, l'annotatore umano 4,7, con un effetto
soffitto sul lato umano (28 domande su 30 valutate 5) che il giudice non
riproduce. Il kappa medio sulle tre metriche è **0,475** ("moderato"),
sotto la soglia di utilizzabilità dichiarata a monte (≥0,61): **per
questo lavoro, i punteggi di fedeltà del giudice automatico non vengono
riportati come misura affidabile**, mentre pertinenza e correttezza sì,
con l'accordo dichiarato accanto al numero. È l'insufficienza stessa,
non solo l'eventuale successo, a essere il risultato: un giudice
automatico non validato a monte avrebbe riportato una fedeltà media
"buona" (3,1/5) senza che nessuno potesse dire se fosse una misura reale
o un artefatto del bias di self-preference.

**Una scomposizione causale dell'errore, non solo una sua misura — misurata
due volte, con due metodi indipendenti.** Sapere che il sistema sbaglia è
meno utile di sapere *dove* sbaglia: il metodo automatico (rango
pre/post-rerank + soglia di correttezza, §6.4, `results/report_FINAL_V2.md`)
attribuisce il 57% degli errori al mancato recupero della fonte, il 3% al
reranking, il 20% a un generatore che sbaglia pur col contesto giusto, il
20% restante a risposte corrette. L'annotatore umano in cieco, leggendo
le stesse 30 domande senza vedere questa classificazione a monte
(`results/annotations_FINAL_V2.json`), arriva a proporzioni diverse ma
alla stessa conclusione qualitativa: 46,7% retrieval_miss, 43,3% ok,
6,7% generation_miss, 3,3% reranker_drop — il retrieval resta la causa
dominante, il reranker quasi irrilevante, ma il metodo automatico
sottostima quante risposte "funzionano" nel complesso rispetto a un
giudizio umano olistico. Questa doppia misura, insieme al test a
contesto oracolo (§6.5, completato), è ciò che permette di distinguere
un limite risolvibile con ingegneria (retrieval, reranking — qui il più
rilevante) da un limite strutturale del vincolo hardware (dimensione del
modello generativo). Un caso
concreto emerso da questo run è anche una scoperta a sé: in una risposta
(Q15) il modello ha ripetuto testualmente l'istruzione di correzione
iniettata nel system prompt dal nodo di self-check invece di limitarsi a
correggere — un bug non documentato prima d'ora, e un indizio
comportamentale del limite del modello da 3B nel seguire istruzioni di
sistema senza trascriverle nell'output.

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

Tre estensioni sono state predisposte a livello di strumentazione ma
deliberatamente non eseguite, per la scarsa incidenza attesa sulla
risposta alla domanda di ricerca rispetto al tempo richiesto: il cambio
del modello di embedding in produzione (i dati del confronto in
`report_compare_embeddings.md` sono direzionalmente favorevoli a
`e5-small` ma non raggiungono la significatività su n=30, §6.4), il
confronto fra modelli generativi locali a contesto congelato
(`benchmarks/compare_generators.py`, script pronto e mai eseguito, misura
qualità e prestazioni hardware separatamente proprio per non confondere
le due cose) e un insieme di controllo held-out per verificare che la
configurazione scelta con l'ablation generalizzi fuori dal golden
dataset v2 (`config/holdout_v1.json`, scaffold predisposto con 10 id ma
mai compilato). Sono collocati fra gli sviluppi futuri (§8.1), non fra i
risultati.

## Chiusura

Il vincolo di esecuzione locale, posto come premessa del lavoro e non come
sua giustificazione a posteriori, si è rivelato produttivo proprio perché
costringe a misurare — non solo ad affermare — quanto costa in accuratezza
la sovranità del dato quando l'alternativa (inviare dati della pubblica
amministrazione a un servizio terzo) non è percorribile. Il test a
contesto oracolo è la risposta diretta a questa domanda: **23,3 punti
percentuali** di risposte corrette in meno sono il prezzo pagato al
modello da 3B parametri su CPU, non all'architettura RAG in sé, che a
parità di contesto corretto risponde correttamente **76,7% delle volte**
— un tasso che la sola pipeline end-to-end, appesantita anche dal 26,7%
di errore imputabile al retrieval, non lascia intravedere. È su questa
distinzione — fra ciò che l'architettura può fare e ciò che l'hardware
disponibile le permette di fare — che si fonda la risposta finale alla
domanda di ricerca: il sistema realizzato è più accurato di quanto la
sua cifra aggregata (50,0% pipeline reale) suggerisca da sola, e la parte
mancante si divide in modo quasi paritario fra un limite ingegneristico
(il retrieval, migliorabile) e un limite strutturale (il generatore,
vincolato dall'hardware).
