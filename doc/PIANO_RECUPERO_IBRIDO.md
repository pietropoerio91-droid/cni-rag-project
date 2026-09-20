# Piano del recupero ibrido — passaggio di consegne

Analisi del 20 settembre 2026, condotta sul run congelato `FINAL_V2`
(`results/2026-08-28/eval_14-12-22.json`) e sul codice al commit `f7da1c6`.

Questo file serve a chi riprende il lavoro sul sistema: contiene la diagnosi, le
modifiche gia' scritte e l'ordine delle verifiche. **Non e' testo da tesi.**

## Vincolo che governa tutto

La tesi si chiude sulla configurazione congelata. Gli esperimenti entrano in tesi
solo se arrivano in tempo; altrimenti restano fra gli sviluppi futuri. Il
deposito dell'elaborato e' il **10 dicembre 2026**, la seduta il **21 gennaio
2027**, e non devono dipendere dall'esito di questi interventi.

Corollario operativo: **non toccare la collection `cni_documents`**, che sostiene
i numeri dei capitoli 3 e 4. Ogni esperimento vive su una collection separata.

---

## Diagnosi: perche' falliscono le 14 domande

Estratto il rango della fonte attesa per ogni domanda con
`error_stage = retrieval_miss`. **In 13 casi su 14 il rango e' `None` gia' fra i
25 candidati densi**: la fonte non entra mai. Non e' un problema di ordinamento,
e' di richiamo al primo stadio.

Cosa chiedono quelle domande:

| domanda | termine richiesto |
|---|---|
| Q01, Q02, Q10 | Perrini · Cappiello · Margiotta |
| Q05 | Via XX Settembre |
| Q12 | 80057570584 (codice fiscale) |
| Q13 | Ufficio Esteri |
| Q22 | Trento · Bolzano |
| Q28 | WFEO |
| Q30 | 12 luglio 2019 |
| Q15 | Transparency International |
| Q19 | ENGINEERS EUROPE |

Sono token lessicali. Un embedding denso non puo' rappresentare `80057570584`:
non esiste un intorno semantico per un numero di undici cifre. Le pagine
bersaglio sono istituzionali, brevi, dense di nomi e povere di prosa.

**Concentrazione**: Q01, Q02 e Q10 attendono la stessa pagina, `cni/consiglio`.
Recuperarla vale tre domande, il 10% del dataset.

## Seconda scoperta: l'ordinamento denso non discrimina

Ricostruito da quale posizione fra i 25 candidati proviene ciascuno dei 5
documenti finali, su tutte e 30 le domande (150 slot):

| provenienza | slot | quota |
|---|---:|---:|
| posizioni 1–10 | 71 | 47,3% |
| posizioni 11–25 | 79 | **52,7%** |
| di cui oltre la 20ª | 22 | 14,7% |

La distribuzione per posizione e' piatta (9, 10, 7, 10, 6, 7, 7, 7, 3, 5, 8, 10,
7, 4, 4, 4, 2, 5, 7, 6, 5, 4, 5, 4, 4): con una selezione uniforme su 25 ci si
attenderebbe 6 per posizione.

Il cross-encoder non sceglie a caso — quando la fonte corretta c'e', la porta in
posizione media 1,4 — ma le sue scelte sono **scorrelate dall'ordine del denso**.
Il primo stadio riempie la stanza, il secondo la ordina.

**Conseguenze**: ridurre `top_k` sotto 25 butterebbe via il 53% del contesto
attuale. E la mossa giusta non e' ordinare meglio, e' **allargare il richiamo**.

## Caso Q15 — tre difetti sovrapposti

Verificato il 20/09. La pagina `/whistleblowing` **e' nel corpus** e la ricerca
densa la trova ai ranghi 1 e 2. Ma il suo testo estratto e' un menu di link:

> Informativa privacy · Procedura Whistleblowing · Modello di segnalazione
> mediante posta ordinaria · Per inviare una segnalazione mediante piattaforma,
> clicca qui: consiglionazionaledegliingegneri.whistleblowing.it

La credit line a Transparency International sta sulla **piattaforma esterna**,
fuori dal dominio `cni.it` e quindi fuori dal perimetro di crawling.
Confermato: `grep -ril "transparency" data/processed/` non trova nulla.

Ne consegue che:

1. La risposta di riferimento di Q15 proviene da **fuori dal corpus**, mentre la
   sezione 3.1 della tesi dichiara che le risposte vengono dai documenti
   indicizzati. E' un'eccezione da dichiarare.
2. Il sistema ha risposto **correttamente** astenendosi, e l'annotazione la conta
   come errata. E' un falso negativo del dataset.
3. La metrica automatica segna `Hit@1 = 1` perche' l'URL sopravvissuto contiene
   `whistleblowing`, mascherando i primi due punti.

Il reranker **non** ha sbagliato: preferire i PDF sulla procedura a un elenco di
link era ragionevole.

Pattern ricorrente su questo corpus: le pagine di approdo del portale CNI sono
spesso menu di collegamenti, e il contenuto informativo sta altrove — in un PDF,
in una sottopagina o su un dominio esterno. Stesso caso di Q22 con
`/cni/ordini-provinciali`.

---

## Cosa e' gia' scritto nel repository

Scritto il 20/09, **non ancora committato** al momento della consegna.

| file | stato |
|---|---|
| `src/rag/sparse_index.py` | nuovo — BM25 su indice invertito in memoria |
| `src/rag/fusion.py` | nuovo — Reciprocal Rank Fusion |
| `src/rag/hybrid_retriever.py` | riscritto — due canali, fusione, taglio a `top_k` |
| `tests/unit/test_sparse_e_fusione.py` | nuovo — 11 test, nessuna dipendenza esterna |
| `config/rag_config.yaml` | blocco `hybrid_search` con parametri che hanno effetto |

Fino a questo momento `hybrid_search` era **dichiarato ma non implementato**:
`dense_weight` veniva letto e mai usato, nessuna componente sparsa esisteva.

**Scelte implementative da conoscere:**

- BM25 nella formulazione di Robertson e Zaragoza, con IDF sempre positiva
  (variante Lucene). Implementato in casa, ~40 righe, nessuna dipendenza nuova:
  in tesi si cita la formula, non una libreria.
- Il tokenizzatore **conserva le cifre** (`80057570584` deve restare cercabile) e
  **ripiega i diacritici** (le domande arrivano con e senza accento).
- Il **titolo entra nel testo indicizzato** (`include_title: true`), perche' molte
  pagine di approdo hanno il tema nel titolo e link nel corpo. Disattivabile per
  misurarne il contributo.
- **RRF invece della somma pesata**: il coseno sta in [-1,1] con soglia, BM25 non
  e' limitato. Lavorando sui ranghi non serve normalizzare ne' calibrare pesi.
- I due canali pescano **50 candidati ciascuno**, la fusione taglia a
  `retrieval.top_k` = 25. Cambia *quali* documenti arrivano al cross-encoder, non
  *quanti*: la latenza non cambia e il confronto con la linea di base resta
  pulito.
- `hybrid_search.enabled` e' **false**: con la bandiera spenta il comportamento e'
  identico alla configurazione congelata.

**Da fare sul repository:**

```
git checkout -b exp/retrieval-ibrido
git add src/rag/sparse_index.py src/rag/fusion.py src/rag/hybrid_retriever.py \
        tests/unit/test_sparse_e_fusione.py config/rag_config.yaml doc/PIANO_RECUPERO_IBRIDO.md
git commit -m "feat(retrieval): canale lessicale BM25 e fusione dei ranghi"
```

---

## Ordine delle verifiche

Il punto che rende tutto economico: **la valutazione del solo recupero
(`run_evaluation.py --no-judge`) dura minuti e non usa l'LLM.** Si puo' quindi
misurare a gradini senza bruciare notti.

| passo | collection | configurazione | costo | cosa isola |
|---|---|---|---|---|
| 0 | `cni_documents` | `enabled: false` | minuti | **non-regressione**: deve dare i numeri di FINAL_V2 |
| 1 | `cni_documents` | `enabled: true` | minuti | **BM25 da solo**, senza reindicizzare nulla |
| 2 | `cni_documents_e5` | e5, `enabled: false` | 73 min + minuti | effetto del troncamento |
| 3 | `cni_documents_e5` | e5, `enabled: true` | minuti | i due insieme |

I passi 0 e 1 non richiedono alcuna indicizzazione: l'indice BM25 si costruisce
dai testi gia' nel payload di Qdrant.

**Il passo 0 e' obbligatorio** prima di guardare qualunque altro numero.

La valutazione end-to-end con generazione (~2,4 h) si lancia **una volta sola**,
sulla configurazione finale. Poi i 90 giudizi umani, che li assegna Pietro
secondo `doc/` e la rubrica di annotazione: Claude definisce il metro, non le
misure.

## L'esperimento e5, separato

Branch `exp/embedding-e5`, tre righe in due file:

- `config/rag_config.yaml`: `embedding.model_name` → `intfloat/multilingual-e5-small`
- `config/rag_config.yaml`: `vector_store.collection_name` → `cni_documents_e5`
- `config/qdrant_config.yaml`: `qdrant.collection_name` → `cni_documents_e5`

Nessuna modifica al codice: i prefissi `query: ` e `passage: ` sono applicati
automaticamente da `PREFISSI_PER_FAMIGLIA` in `src/core/model_factory.py`.
Dimensionalita' invariata (384), quindi la forma della collection non cambia.

**Verifica obbligatoria all'avvio dell'indicizzazione**: nel log deve comparire
`Embedding prefixes: query='query: ' document='passage: '`. Se dice
`none (symmetric model)`, il modello non e' stato riconosciuto e si sta
costruendo un indice silenziosamente degradato.

**Cancello prima della notte**: la valutazione del solo recupero deve dare
Hit@5 ≈ 46,7% e MRR ≈ 0,378, cioe' i valori del confronto del 28/08
(`results/report_compare_embeddings.md`). Se non combacia, l'indice e' costruito
male.

Effetto per domanda atteso, dal confronto di agosto: migliorano Q05 (MRR 0→1),
Q17 (0→1), Q19 (0→0,33), Q11 (0→0,5); Q21 risale da 0,33 a 1. **Peggiorano Q08**
(0,5→0, oggi corretta: regressione da cercare) e Q29 (0,5→0, gia' sbagliata).

---

## Trappole operative

- **Qdrant in modalita' locale e' embedded e prende un lock esclusivo** su
  `./data/qdrant_db`: un solo processo alla volta. Fermare l'API prima di
  indicizzare e riavviarla dopo — `QdrantClientManager` e' un singleton e legge
  il nome della collection una volta sola, all'avvio.
- **Le collection sono indipendenti**: creare `cni_documents_e5` non tocca
  `cni_documents`. ~100 MB l'una. Per tornare indietro basta rimettere il nome.
- **Mai `--clear` per abitudine**: azzera la collection corrente, cioe' 73 minuti
  di lavoro.
- **Non cambiare due cose insieme**: senza attribuzione il risultato non e'
  raccontabile in tesi.
- **Reindicizzare non e' ricrawlare**: `build_index.py` legge da `data/processed`,
  il crawler non entra in gioco.

## Terzo intervento, da tenere per ultimo: copertura del corpus

Le 212 schede territoriali sotto `/area-cni` non sono nel corpus. Resa sulle 30
domande: **una domanda, forse tre** (Q22 certamente; Q23 e Q30 dipendono da dove
stia `area-giurisdizionale` sul portale).

Va per ultimo perche' e' l'unico che **cambia il corpus**, quindi la base di
tutti i numeri dei capitoli 3 e 4.

**Come farlo in sicurezza**: `Downloader.save_document` scrive un JSON per URL e
non cancella mai nulla; `load_documents` legge tutti i `.json` della cartella.
Quindi un **crawl mirato** alla sola zona mancante, salvato in `data/processed`,
**aggiunge** i file nuovi e lascia intatti i 4.144 esistenti.

⚠️ La whitelist deve contenere anche **la strada**, non solo la destinazione: il
crawler parte dalla home e segue i link, e le schede si raggiungono da
`/cni/ordini-provinciali`. Serve almeno `["/area-cni", "/cni"]`.

⚠️ **Un ricrawl completo con la whitelist attuale sarebbe distruttivo.**
Verificato sugli URL del run FINAL_V2: `included_paths` vale
`["/media-ing", "/cni", "/temi", "/contatti", "/servizi"]` e **119 URL su 445
(27%) verrebbero persi** — fra cui `/images` (85 URL, i PDF), `/albo-unico`
(fonte attesa di Q29), `/whistleblowing` (fonte attesa di Q15), `/urp`,
`/sezioni-amministrazione-trasparente`.

Nota di governance: fra gli URL indicizzati ce ne sono **due sotto
`/login-interno`**. In un corpus dichiarato di soli dati pubblici, meritano una
verifica.

---

## Limite che nessun intervento supera

Con n = 30 la potenza statistica e' intorno al 5%: **nessun miglioramento sara'
significativo**, quale che sia. Un movimento di cinque domande (43% → 60%)
sarebbe visibile senza statistica, ma va dichiarato come descrittivo.

L'ampliamento del golden dataset resta il primo degli sviluppi futuri, e l'unico
intervento che cambierebbe questa situazione.
