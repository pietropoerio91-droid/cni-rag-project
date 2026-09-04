# Run FINAL_V2 — valutazione end-to-end, golden dataset v2 (n=30)

Eseguito 28/08/2026, 30 domande, durata 142,7 minuti. Giudice: `qwen2.5:3b`
(stesso modello del generatore — **punteggi qualitativi non ancora
validati**, serve l'annotazione umana in cieco prima di poterli citare
in tesi con fiducia). Stato del repository al momento del run: dirty
(alcune modifiche non committate, elencate nel file JSON sotto `git`).

## Retrieval — pre e post reranking (IC 95%)

| Metrica | Candidati (pre-rerank) | Contesto LLM (post-rerank) |
|---|---|---|
| Hit@3 | 20,0% [9,5%, 37,3%] | 40,0% [24,6%, 57,7%] |
| Hit@5 | 26,7% [14,2%, 44,5%] | 40,0% [24,6%, 57,7%] |
| MRR | 0,213 [0,091, 0,354] | 0,294 [0,161, 0,439] |
| Recall@5 | 0,267 [0,100, 0,433] | 0,400 [0,233, 0,567] |
| nDCG@5 | 0,172 [0,069, 0,288] | 0,325 [0,180, 0,477] |

Effetto del reranker (confronto appaiato): migliora nDCG@5 in modo
significativo (+0,152, p=0,005, effetto piccolo) e Recall@5 (+0,133,
p=0,046), ma non raggiunge la significatività su Hit@5 (p=0,125) né MRR
(p=0,123) a questa numerosità.

## Generazione (IC 95%)

| Metrica | Valore |
|---|---|
| Fallback esplicito | 0,0% [0,0%, 11,4%] |
| Must-contain superato | 50,0% [33,2%, 66,8%] |
| Fedeltà (0-5) | 3,100 [2,433, 3,767] |
| Pertinenza (0-5) | 2,767 [2,067, 3,433] |
| **Correttezza (0-5)** | **1,333 [0,733, 1,967]**, mediana 0 |
| Latenza media | 200,4s [182,4, 219,7] |

## Decomposizione dell'errore per stadio (§6.4)

Classificazione per domanda: `fallback` se il sistema ha dichiarato di non
sapere; `retrieval_miss` se la fonte attesa non è mai entrata nei
candidati pre-rerank; `reranker_drop` se era nei candidati ma il reranker
l'ha esclusa dal contesto finale; `generation_miss` se era nel contesto ma
la risposta resta scorretta (correttezza < 4); `ok` se correttezza ≥ 4.

| Stadio | n | % |
|---|---:|---:|
| **retrieval_miss** | **17** | **57%** |
| ok | 6 | 20% |
| generation_miss | 6 | 20% |
| reranker_drop | 1 | 3% |

**Il collo di bottiglia dominante è il retrieval**, non il reranking né la
generazione: in 17 domande su 30 la fonte corretta non entra mai fra i 25
candidati della ricerca densa — il reranker e il generatore non hanno
nessuna possibilità di recuperarla, qualunque sia la loro qualità. Il
reranker droppa un solo caso (Q09) fra quelli che aveva ricevuto. La
generazione fallisce su 6 casi pur avendo il contesto corretto — è
esattamente la quota che il test a contesto oracolo (§6.5) deve
quantificare con precisione, isolando il limite del modello da 3B.

## Due casi di studio

**Q01 — "Chi è il presidente del CNI?"** Il sistema risponde *"Armando
Zambrano"* (un ex presidente, non l'attuale). `rank_pre=None,
rank_ctx=None`: la fonte corretta (Perrini) non è mai entrata nei
candidati. In FULL1 (24/08, filtro di categoria ancora attivo) la stessa
domanda otteneva `rank=8` e rispondeva correttamente — la disattivazione
del filtro (27/08, motivata dall'ablation) qui costa la risposta giusta:
il filtro compensava, per questa domanda specifica, la debolezza nota del
chunk (dominato da testo biografico, si classifica intorno al rango 20-21
su tutto il corpus non filtrato). Trade-off reale fra copertura media e
casi singoli, non un bug.

**Q15 — "Chi promuove la piattaforma di whistleblowing del CNI?"** La
risposta generata inizia con: *"La risposta precedente conteneva
imprecisioni o allucinazioni. Basandomi esclusivamente sui documenti
forniti…"* — questo è il testo dell'istruzione di correzione che
`rag_chain.py` (nodo `_generate`) inietta nel **system prompt** quando
scatta un fix dopo un `self_check` negativo; non dovrebbe mai comparire
nella risposta visibile. Il modello l'ha ripetuta invece di limitarsi a
correggere. **Bug non documentato prima d'ora**, riproducibile
(`results/2026-08-28/eval_14-12-22.json`, Q15). Buona anche come
evidenza comportamentale del limite del modello da 3B nel seguire
istruzioni di sistema senza trascriverle nell'output.

## Nota di riproducibilità

Il repository non era pulito al momento del run (`git.dirty: true`) —
file modificati elencati nel JSON sotto `git.file_modificati`. Nessuno di
questi risulta rilevante per la pipeline di query (sono script di
benchmark/dati sperimentali paralleli), ma va dichiarato per trasparenza.
