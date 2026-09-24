# Conclusioni — MATERIALE DI LAVORO, NON TESTO DA CONSEGNARE

> ⚠️ **Questo file è un appunto tecnico, non una bozza da incollare nella
> tesi.** L'uso di AI concordato per questo progetto copre lo sviluppo del
> sistema (codice, benchmark, fix, esperimenti), non la stesura del testo
> della tesi, che passa per un controllo antiplagio. Il capitolo Conclusioni
> va scritto da Pietro con le proprie parole; questo documento tiene
> allineati i dati, la struttura logica e le cautele da dichiarare.
>
> Per questo, dal 23/09, il file è scritto per punti: numeri, fonti e
> ragionamento, non prosa pronta.

> **Aggiornamento 23/09/2026.** Il run di riferimento è **`FINAL_V3`**
> (`results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json`, riepilogo in
> `results/2026-09-22/RIEPILOGO_FINAL_V3.md`). `FINAL_V2` resta come termine
> di confronto. La versione precedente di questo file, tutta su `FINAL_V2`, è
> in `archivio/CONCLUSIONI_TESI_2026-09-03.md`. In fondo c'è l'elenco di cosa
> è cambiato e perché.

---

## Fonti dei numeri

| Dato | Fonte |
|---|---|
| Recupero, generazione, giudice automatico di `FINAL_V3` | `results/2026-09-22/eval_FINAL_V3_DEFINITIVO.json` (`aggregate`) |
| Accuratezza umana e tassonomia degli errori di `FINAL_V3` | stesso file, `valutazione_umana`; annotazioni in `results/annotations_FINAL_V3_DEFINITIVO.json` |
| Confronto appaiato `FINAL_V2` → `FINAL_V3` | stesso file, `confronto_vs_FINAL_V2`; tabelle in `RIEPILOGO_FINAL_V3.md` |
| Accordo giudice-umano di `FINAL_V3` | `results/judge_agreement_2026-09-22.json`; `RIEPILOGO_FINAL_V3.md` §4 |
| `FINAL_V2` (28/08) | `results/report_FINAL_V2.md`, `results/annotations_FINAL_V2.json` |
| Test a contesto oracolo | `results/oracle_context_2026-08-28_14-35.json` (**eseguito una sola volta, all'epoca di `FINAL_V2`**) |
| Come si è arrivati alla configurazione finale | `doc/TEST_RECUPERO_IBRIDO.md` |

Configurazione di `FINAL_V3`: embedding `intfloat/multilingual-e5-small`,
recupero ibrido (denso + BM25 nativo in Qdrant, RRF k=60), reranker
`BAAI/bge-reranker-base`, generatore `qwen2.5:3b`, filtro PII disattivato.
Tag `congelato-2026-09-21-e5`. N=30 domande del golden dataset v2.

---

## Risposta alla domanda di ricerca

La domanda ha due parti: **con quale accuratezza** risponde un sistema RAG
interamente locale sui dati pubblici del CNI, e **quanta parte dell'errore
residuo** è dovuta ai vincoli hardware dell'esecuzione in locale.

### Parte 1 — accuratezza

| Misura (n=30) | FINAL_V2 | **FINAL_V3** | Confronto appaiato |
|---|---:|---:|---|
| **Accuratezza umana** (correttezza ≥ 4) | 43,3% (13/30) | **63,3% (19/30)** [45,5%, 78,1%] | +20,0 punti, McNemar p=0,146 |
| Correttezza umana media (0-5) | 2,27 | **3,57** | +1,30, Wilcoxon p=0,0085 |
| Hit@5 sul contesto passato al generatore | 40,0% | **60,0%** [42,3%, 75,4%] | +20,0 punti, p=0,070 |
| MRR | 0,294 | **0,434** [0,284, 0,591] | +0,140, p=0,028 |
| Risposte che contengono il dato atteso (*must-contain*, metrica deterministica) | 50,0% | **66,7%** [48,8%, 80,8%] | — |

- La correttezza media di V2 nel confronto appaiato è **2,27**: la domanda Q09,
  annotata senza voto di correttezza, conta 0 come nell'accuratezza (43,3%). Il
  2,35 che compare altrove è la media sulle sole domande con il voto compilato.
  In tesi usare 2,27 accanto al Δ +1,30, altrimenti i numeri non tornano.
- L'**accuratezza umana** è il risultato principale da riportare. Quella del
  giudice automatico non è validata (vedi sotto).
- Nessun confronto è significativo con n=30 nel senso della potenza
  statistica classica. I p-value sono descrittivi. La differenza sulla
  correttezza media (p=0,0085) è la più netta, ma resta una misura su 30
  domande.
- **Da dichiarare:** `FINAL_V2` girava in realtà con `all-MiniLM-L6-v2`
  (embedding inglese), non con il modello multilingue dichiarato nel suo
  `config_snapshot`: una variabile d'ambiente sovrascriveva il YAML
  (`SISTEMA.md` §11.5). Il confronto V2→V3 cambia quindi più di un fattore:
  embedding, canale BM25 e filtro PII.

### Dove sbaglia il sistema — tassonomia degli errori (annotazione umana in cieco)

| Stadio | FINAL_V2 | **FINAL_V3** |
|---|---:|---:|
| `ok` | 13 (43%) | **19 (63%)** |
| `retrieval_miss` (fonte mai fra i candidati) | 14 (47%) | **2 (7%)** |
| `reranker_drop` (recuperata, scartata dal reranker) | 1 (3%) | **1 (3%)** |
| `generation_miss` (contesto giusto, risposta sbagliata) | 2 (7%) | **8 (27%)** |

- **Il collo di bottiglia si è spostato.** In `FINAL_V2` l'errore era quasi
  tutto a monte: 15 errori di recupero contro 2 di generazione. In `FINAL_V3`
  è per lo più a valle: 3 contro 8. I `retrieval_miss` scendono da 14 a 2, e
  i 2 rimasti (Q13, Q22) erano già `retrieval_miss` in V2: **il recupero
  ibrido ha risolto 12 dei 14 casi senza crearne di nuovi** (verificato il
  24/09 sulle annotazioni dei due run; vista Qualitative › Confronto per
  domanda della dashboard).
- **Non tutto migliora:** domanda per domanda, 9 migliorate, 3 peggiorate, 18
  invariate. Le 3 peggiorate (Q18, Q21, Q24) sono tutte `generation_miss`
  in V3: il contesto giusto c'era, la risposta no. È coerente con lo
  spostamento del collo di bottiglia sul generatore e va dichiarato.
- Il dato **va letto nel modo giusto**: gli errori di generazione non sono
  aumentati perché il generatore è peggiorato (è lo stesso modello). Ora
  arrivano al generatore domande con il contesto giusto che prima fallivano
  già al recupero, e una parte di queste il modello da 3B non la risolve.
- Casi rivisti sui dati grezzi, da citare se servono: Q12 è `generation_miss`
  (dato presente nel contesto, non estratto); Q02 è `reranker_drop` (fonte
  al rango 22); Q22 e Q24 sono falsi negativi della metrica automatica
  (`RIEPILOGO_FINAL_V3.md` §5).

### Parte 2 — quanto pesa il vincolo hardware

- **Il test a contesto oracolo è stato eseguito una sola volta, il 28/08,
  con la configurazione di `FINAL_V2`, e non è stato ripetuto.** Risultato:
  fornendo al generatore il documento giusto per costruzione, il
  *must-contain* arriva al **76,7% [59,1%, 88,2%]** contro il 50,0% della
  pipeline di allora (McNemar p=0,115, non significativo).
- Il test misura il **tetto del generatore** (contesto giusto garantito),
  che non dipende dal recupero. Con la pipeline di `FINAL_V3` al 66,7% di
  *must-contain*, la distanza dal tetto scende da 26,7 a circa **10 punti**,
  mentre i **23,3 punti** che mancano anche col contesto oracolo restano il
  limite del generatore.
- **Cautela obbligatoria:** questo confronto accosta due esecuzioni diverse
  (oracolo del 28/08, pipeline del 22/09) e non è una misura appaiata. Inoltre
  il test oracolo girava con il filtro PII attivo, che rendeva impossibili
  Q06 e Q12 (`SISTEMA.md` §11.9): il tetto reale del generatore potrebbe
  essere un po' più alto. Va presentato come stima indicativa, non come
  numero misurato.
- La lettura qualitativa è coerente con la tassonomia umana: in `FINAL_V2`
  la parte mancante si divideva quasi a metà fra recupero (26,7) e generatore
  (23,3); dopo il recupero ibrido, la quota imputabile al recupero si riduce
  e **la parte dominante dell'errore residuo è il generatore da 3B su CPU**,
  cioè il vincolo hardware della domanda di ricerca.

---

## Il giudice automatico: validato e non affidabile

| Metrica | kappa FINAL_V2 | **kappa FINAL_V3** |
|---|---:|---:|
| Fedeltà | -0,019 | 0,283 |
| Pertinenza | 0,770 | **0,865** |
| Correttezza | 0,674 | **0,471** |
| Media | 0,475 | **0,54** |

- Su `FINAL_V3` il kappa medio è **0,54**, ancora **sotto la soglia di
  utilizzabilità dichiarata a monte (0,61)**. Solo la pertinenza ha un
  accordo alto (0,865).
- **Da correggere rispetto alla versione del 03/09:** allora la correttezza
  del giudice era "riportabile con calibrazione" (kappa 0,674). Su
  `FINAL_V3` la correttezza scende a 0,471 e **non è più riportabile** come
  misura affidabile. Per questo il risultato principale è l'accuratezza
  umana. La correttezza media del giudice su V3 (1,90/5) resta molto sotto
  quella umana (3,57/5), come già in V2 (1,33 contro 2,35).
- Giudice e generatore sono lo stesso modello (`qwen2.5:3b`): il rischio di
  bias di self-preference era dichiarato a monte ed è confermato dal
  mancato accordo. Il risultato va presentato come esito della validazione,
  non nascosto.

---

## Il contributo del lavoro — punti da sviluppare

1. **Metriche validate prima di essere usate.** Il caso guida è Q01 ("Chi è
   il presidente del CNI?"): il benchmark a keyword la dava corretta mentre il
   sistema rispondeva di non saperlo. Da lì viene il principio di validare
   ogni metrica contro casi noti. Sono seguiti altri episodi dello stesso
   tipo: ground truth circolare, recall non troncato, match per sottostringa
   (Q22 e Q24 in `FINAL_V3`). Storia completa in `INDICE_TESI.md`, sezione Q01.
2. **Una configurazione dichiarata non è una configurazione eseguita.** È la
   scoperta più forte del lavoro: `FINAL_V2` è stato misurato con un
   embedding diverso da quello dichiarato. Conseguenza pratica: ogni run ora
   registra l'embedding effettivo (`embedding_effettivo`) e, dal 23/09, la
   collection interrogata.
3. **Un giudice automatico che dichiara i propri limiti.** Misurato due volte
   contro l'annotazione umana in cieco (V2 e V3), non raggiunge la soglia in
   nessuna delle due: sarebbe stato facile riportarne i numeri.
4. **Una scomposizione causale dell'errore che ha guidato un intervento.**
   La tassonomia di `FINAL_V2` indicava il recupero (47% `retrieval_miss`); la
   diagnosi successiva ha mostrato che in 13 casi su 14 la fonte non entrava
   fra i candidati densi, e il termine cercato era quasi sempre lessicale
   (nomi, codici, date, per esempio il codice fiscale `80057570584`): fuori
   dalla portata di un embedding (`SISTEMA.md` §12). L'intervento
   mirato (BM25 fuso con RRF) ha portato l'accuratezza umana dal 43,3% al
   63,3% e ha spostato il collo di bottiglia sul generatore. È il ciclo
   misura → diagnosi → intervento → rimisura, non una lista di tentativi.
5. **Un comportamento anomalo documentato.** In `FINAL_V2`, Q15: il modello
   ha ripetuto testualmente l'istruzione di correzione del nodo di
   self-check invece di applicarla. È un indizio dei limiti del 3B nel
   seguire istruzioni di sistema. *Da verificare se ricorre in `FINAL_V3`
   prima di citarlo come comportamento stabile.*

---

## Limiti — gerarchia

1. **Dimensione del golden dataset (n=30).** Resta il limite principale:
   nessun confronto raggiunge la potenza statistica classica, nemmeno il
   +20 punti di accuratezza V2→V3 (p=0,146). Per una potenza dell'80% serve
   un dataset di circa 500 domande (`INDICE_TESI.md` §6.3).
2. **Selezione sul set di valutazione.** La configurazione finale (e5,
   BM25, reranker) è stata scelta confrontando varianti sulle **stesse 30
   domande** su cui poi è misurata. Il 63,3% è quindi probabilmente una stima
   ottimistica. L'insieme di controllo indipendente (`config/holdout_v1.json`)
   è predisposto ma mai compilato né eseguito.
3. **Assunzione non verificata sul reranker.** Il confronto fra reranker è
   stato fatto su un embedding poi cambiato; che la scelta regga anche con
   e5 è un'assunzione (`TEST_RECUPERO_IBRIDO.md`, esperimenti §5 e §8, come
   indicato in `INDICE_TESI.md` §6.2).
4. **Giudice automatico non validato** (kappa medio 0,54 < 0,61): i risultati
   poggiano sull'annotazione di un solo annotatore umano.
5. **Portata:** un solo corpus (dati pubblici CNI) e una sola piattaforma
   hardware. Il corpus del run (13.784 chunk da 4.144 documenti) non include
   `/area-cni`, configurata solo per la prossima indicizzazione.

**Limiti della versione precedente che non valgono più (non riportarli):**
- ~~"assenza di ricerca ibrida"~~: implementata, misurata e adottata il 21-22/09;
- ~~"cambio dell'embedding in produzione non eseguito"~~: fatto (e5-small);
- ~~limiti tecnici di `SISTEMA.md` §11.7-§11.10~~: chiusi il 23/09, senza
  effetto sui numeri (vedi `INDICE_TESI.md` §6.2).

**Ancora non eseguiti, da collocare fra gli sviluppi futuri:** il confronto
fra generatori locali (`benchmarks/compare_generators.py`, script pronto,
mai eseguito), l'insieme di controllo held-out, e il boost morbido di
categoria al posto del filtro rigido.

---

## Chiusura — il filo logico

- La premessa (esecuzione locale per sovranità del dato della pubblica
  amministrazione) si traduce in una domanda misurabile: quanto costa in
  accuratezza.
- **Risposta con i dati finali:** il sistema risponde correttamente al
  **63,3%** delle domande (giudizio umano). Il recupero, che era il limite
  dominante, è stato in gran parte risolto con un intervento di ingegneria
  (BM25 ibrido). **Quello che resta è in prevalenza il limite del generatore
  da 3B su CPU**, cioè il prezzo del vincolo hardware.
- Il test oracolo (76,7% col contesto giusto) indica dov'è il tetto del
  generatore attuale. Va dichiarato che non è stato ripetuto sulla
  configurazione finale.
- I tre punti da non perdere nella scrittura: (a) la distinzione fra limite
  ingegneristico (recupero, risolvibile e risolto in parte) e limite
  strutturale (generatore, legato all'hardware); (b) l'onestà metodologica
  (giudice non validato, configurazione dichiarata diversa da quella
  eseguita, selezione sul set di valutazione); (c) n=30 come limite che
  qualifica ogni numero.

---

## Cosa è cambiato rispetto alla versione del 03/09

| Punto | Prima (FINAL_V2) | Ora (FINAL_V3) |
|---|---|---|
| Run di riferimento | `FINAL_V2`, 28/08 | `FINAL_V3_DEFINITIVO`, 22/09 |
| Accuratezza da riportare | Hit@5 40,0% e correttezza del giudice 1,33/5 | **accuratezza umana 63,3%** |
| Collo di bottiglia | recupero (47% `retrieval_miss`) | **generatore** (27% `generation_miss`, recupero al 7%) |
| Correttezza del giudice | riportabile con calibrazione (kappa 0,674) | **non riportabile** (kappa 0,471) |
| Test oracolo | 26,7 recupero / 23,3 generatore, misurati | stessi numeri, **da dichiarare non rimisurati**; con V3 la quota del recupero scende a circa 10 punti (stima) |
| Ricerca ibrida | "limite per scelta, sviluppo futuro" | implementata e adottata |
| Embedding di V2 | descritto come multilingue | in realtà `all-MiniLM-L6-v2` inglese, **da dichiarare** |
| Scomposizione automatica per rango (57% / 20% / 3% di V2) | riportata accanto a quella umana | non ricalcolata per V3: usare la tassonomia umana |
