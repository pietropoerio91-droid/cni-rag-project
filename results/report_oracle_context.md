# Test a contesto oracolo — golden dataset v2 (n=30)

Eseguito 28/08/2026 (`results/oracle_context_2026-08-28_14-35.json`),
confrontato contro il run end-to-end `FINAL_V2`
(`results/2026-08-28/eval_14-12-22.json`). Per ogni domanda, al modello
viene passato direttamente il chunk della fonte attesa che contiene più
termini di `must_contain` — il retrieval è bypassato per costruzione.

## Risultato

Tutte e 30 le domande hanno un **oracolo forte** (il chunk della fonte
attesa contiene davvero i termini chiave; nessun caso di "oracolo debole"
o "assente dal corpus" — il dato non manca mai, il problema è sempre a
valle di questo).

| Componente | Quota | IC 95% |
|---|---:|---|
| Risposte corrette, pipeline reale (must-contain) | 50,0% | [33,2%, 66,8%] |
| Risposte corrette, contesto oracolo (must-contain) | 76,7% | [59,1%, 88,2%] |
| **Perso nel retrieval** | **26,7%** | — |
| **Limite del generatore** | **23,3%** | — |

Test appaiato (McNemar esatto): 20 domande discordanti su 30 (14 in cui
solo l'oracolo riesce, 6 in cui solo la pipeline reale riesce — quest'
ultimo caso è di per sé interessante, il retrieval reale batte l'oracolo
su 6 domande, verosimilmente per differenze nel numero di chunk di
contesto). p=0,115, **non significativo a n=30** — effetto piccolo per il
delta di Cliff (0,267). Latenza media col solo oracolo: 22,6s/domanda
(contro 200,4s della pipeline reale — la differenza è quasi interamente
il costo del retrieval e del reranking, non della generazione).

## Lettura

Il generatore da 3B, anche quando riceve il documento corretto per
costruzione, sbaglia comunque **23,3 domande su 100**: è il costo diretto
del vincolo hardware (nessuna GPU, 8 GB RAM condivisi), non un problema
di retrieval. Il retrieval, dal canto suo, costa **26,7 punti** — una
quota leggermente maggiore, e per costruzione più aggredibile con
interventi engineering (modello di embedding, chunking, filtri) piuttosto
che cambiando piattaforma.

La significatività statistica non raggiunta (p=0,115) va letta insieme
all'ampiezza degli intervalli di confidenza: con n=30 e 20 domande
discordanti su 30, il test ha comunque una potenza limitata. Il segno
della differenza è coerente e sostanzioso (+26,7 punti), ma il singolo
esperimento non basta da solo a escludere il caso; è coerente con il
limite di potenza già discusso per l'ablation study.
