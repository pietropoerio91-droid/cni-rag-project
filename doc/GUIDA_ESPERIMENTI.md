# Guida agli esperimenti — cosa abbiamo misurato e perché

> Documento di riferimento, non testo da consegnare: spiega la logica dei
> quattro esperimenti e il significato di ogni numero prodotto. I dati
> completi, con intervalli di confidenza e test statistici, sono nei
> quattro report in `results/report_*.md`; qui c'è la spiegazione e il
> collegamento fra le parti.

---

## Perché quattro esperimenti, in questo ordine

Non sono quattro misure indipendenti — sono una catena: ognuno risponde
alla domanda che il precedente lascia aperta.

```
1. Quanto è accurato il sistema oggi?          → valutazione end-to-end
2. Perché non è più accurato di così?          → test a contesto oracolo
3. Le scelte di configurazione sono fondate?    → ablation study
4. C'è un modo per migliorare il retrieval?     → confronto embedding
```

---

## 1. Valutazione end-to-end (`FINAL_V2`)

**File**: `results/report_FINAL_V2.md` · `results/2026-08-28/eval_14-12-22.json`

**Cosa fa**: manda le 30 domande del golden dataset attraverso il sistema
completo, così come lo userebbe un utente reale — crawler già fatto,
indice già costruito, ricerca, reranking, generazione, tutto in sequenza.
Eseguita il 28/08, con `category_filter: false` (configurazione attuale
di produzione, non una versione precedente).

**Perché serve**: è la fotografia di base. Senza questo numero non hai un
punto di partenza per ragionare su nient'altro.

**I numeri e cosa vogliono dire**:

| Dato | Valore | Didascalia |
|---|---|---|
| Hit@5 | 40,0% [24,6%, 57,7%] | Su 30 domande, nel 40% dei casi la fonte corretta compare fra i 5 documenti passati al generatore. L'intervallo fra parentesi è quanto potrebbe variare il vero valore con un altro campione di domande — è largo perché n=30 è piccolo |
| MRR | 0,294 | Quanto in alto, in media, si piazza la prima fonte corretta nella lista dei candidati. 1,0 = sempre al primo posto; più basso = più in fondo o assente |
| Correttezza | 1,33/5 (mediana 0) | Punteggio del giudice automatico su quanto la risposta coincide col fatto vero. La mediana 0 dice che *più della metà* delle domande ha preso il punteggio minimo |
| Must-contain | 50,0% | Controllo oggettivo (non un giudizio): la risposta contiene le parole/fatti chiave attesi? Sì o no, niente sfumature — il dato più affidabile perché non richiede un giudice |
| Decomposizione errore | 57% retrieval_miss, 20% generation_miss, 3% reranker_drop, 20% ok | Per ogni domanda, *dove* si perde la risposta: mai trovata (57%), trovata ma la generazione sbaglia comunque (20%), trovata ma scartata dal reranker (3%), tutto giusto (20%) |

**Cosa NON dice da sola**: perché la generazione sbaglia quando ha il
contesto giusto (quel 20% di `generation_miss`) — per quello serve
l'esperimento successivo.

---

## 2. Test a contesto oracolo

**File**: `results/report_oracle_context.md` · `results/oracle_context_2026-08-28_14-35.json`

**Cosa fa**: stesse 30 domande, ma il retrieval viene bypassato — il
chunk con la risposta viene dato *direttamente* al generatore, scelto a
mano dal golden dataset (non trovato dal sistema).

**Perché serve**: isola la causa dell'errore. Se il sistema risponde bene
col documento giusto in mano, il problema di prima era il retrieval. Se
sbaglia comunque, il problema è il generatore.

**I numeri e cosa vogliono dire**:

| Dato | Valore | Didascalia |
|---|---|---|
| Oracolo forte, 30/30 | — | Per tutte le 30 domande il chunk scelto contiene davvero i fatti chiave (nessun caso di "informazione assente dal corpus") — il confronto è pulito, non falsato da domande senza risposta nei dati |
| Corrette con oracolo | 76,7% [59,1%, 88,2%] | Con il documento perfetto, il sistema risponde bene 3 domande su 4 |
| Corrette pipeline reale | 50,0% | Stesso identico criterio (must-contain) della valutazione end-to-end — confrontabile direttamente |
| **Perso nel retrieval** | **26,7 punti** | Differenza fra le due righe sopra: quanto costa non trovare sempre il documento giusto |
| **Limite del generatore** | **23,3 punti** | Quello che resta anche con tutto giusto in mano: il modello da 3B, su CPU senza GPU, non ce la fa comunque in quasi un quarto dei casi |
| p = 0,115 (McNemar) | non significativo | Il test statistico non riesce a escludere che parte della differenza sia rumore campionario — va dichiarato, non nascosto |

**Perché questo è il risultato più importante della tesi**: risponde
direttamente alla seconda metà della domanda di ricerca — quanto pesa il
vincolo hardware sull'errore finale. Nessun altro esperimento dà questo
numero.

---

## 3. Ablation study

**File**: `results/report_ablation_2026-08-27.md` · due run del 27/08

**Cosa fa**: accende/spegne una alla volta tre scelte di configurazione
— filtro di categoria, reranker, `top_k` — e misura l'effetto sul solo
retrieval (niente generazione, così è veloce: minuti, non ore).

**Perché serve**: il sistema ha scelte di progettazione prese nel tempo.
L'ablation le verifica con dati invece di darle per buone.

**I numeri e cosa vogliono dire**:

| Dato | Valore | Didascalia |
|---|---|---|
| Hit@5 senza filtro | 40,0% | Coerente con `FINAL_V2` — stessa configurazione, stesso risultato, buon segno di riproducibilità |
| Hit@5 con filtro | 33,3%–36,7% (due run) | Punto stimato più basso, ma con IC che si sovrappone ampiamente a quello senza filtro |
| p sempre > 0,05 su ogni metrica | non significativo | Nessuna delle tre scelte testate (filtro, reranker, top_k) mostra un effetto che il test statistico possa confermare a n=30 |
| Effetto reranker | migliora nDCG@5 (p=0,005) e Recall@5 (p=0,046) | Le uniche due differenze che *raggiungono* la significatività in questo esperimento — il reranker aiuta, misurabilmente |

**Perché conta anche senza risultati "positivi"**: dimostra con prove che
30 domande sono oggettivamente poche per distinguere configurazioni con
differenze di questa entità — è il limite più importante dichiarato
nella tesi, e qui lo vedi misurato, non solo affermato.

---

## 4. Confronto fra modelli di embedding

**File**: `results/report_compare_embeddings.md` · `results/compare_embeddings_2026-08-28_16-39.json`

**Cosa fa**: confronta il modello di embedding attuale
(`paraphrase-multilingual-MiniLM-L12-v2`, finestra 128 token) con un
candidato (`intfloat/multilingual-e5-small`, finestra 512 token) sulle
stesse 30 domande.

**Perché serve**: nasce da una scoperta fatta durante il lavoro — il
modello attuale tronca l'82% dei chunk indicizzati perché la sua
finestra (128 token) è troppo corta rispetto alla lunghezza media dei
chunk (266 token). Il confronto verifica se un modello con finestra più
ampia aiuta davvero.

**I numeri e cosa vogliono dire**:

| Dato | Valore | Didascalia |
|---|---|---|
| Hit@5 attuale | 40,0% | Identico a `FINAL_V2` — conferma che il confronto è misurato correttamente |
| Hit@5 candidato | 46,7% | Punto stimato più alto su ogni metrica testata |
| p = 0,17–0,69 | non significativo | Come per l'ablation: trend positivo, non dimostrato con certezza statistica a n=30 |
| Finestra: 512 vs 128 token | fatto verificato | Non è una stima statistica — è una proprietà nota del modello. Con 512 token il troncamento sui vostri chunk (mediana 266 token) sparirebbe quasi del tutto |

**Perché non l'abbiamo adottato**: cambiarlo davvero richiederebbe
re-indicizzare tutta la produzione (~73 minuti) e rilanciare l'intera
valutazione con generazione (~2,4 ore) — costo non giustificato da un
miglioramento non ancora dimostrato con certezza, a ridosso della
scadenza. Resta una raccomandazione motivata per il capitolo sviluppi
futuri, non un'adozione.

---

## Il filo che tiene insieme tutto

| Esperimento | Risponde a | Esito onesto |
|---|---|---|
| 1. End-to-end | Quanto è accurato oggi? | 40% Hit@5, 50% must-contain — moderato, non impressionante da solo |
| 2. Oracolo | Perché non di più? | 26,7% retrieval, 23,3% hardware — la risposta quantificata alla domanda di ricerca |
| 3. Ablation | Le scelte sono fondate? | Trend coerenti, mai significativi a n=30 — limite dichiarato con prove |
| 4. Embedding | Si può migliorare? | Sì probabilmente, non ancora dimostrato — raccomandazione per il futuro |

Il valore della tesi non sta nell'avere un sistema molto accurato — non
lo è particolarmente. Sta nell'aver **misurato con rigore quanto lo è e
perché**, separando quello che è colpa di scelte ingegneristiche
(migliorabili) da quello che è costo diretto del vincolo hardware
(strutturale), e dichiarando onestamente dove il campione non basta a
essere certi.
