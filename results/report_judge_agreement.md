# Accordo giudice automatico vs annotazione umana — golden dataset v2 (n=30)

Eseguito 02-03/09/2026: annotazione umana in cieco (`results/annotations_FINAL_V2.json`)
sul run `FINAL_V2` (28/08), confrontata con i punteggi del giudice automatico
(`qwen2.5:3b` — lo stesso modello usato per la generazione). Report completo
in `results/judge_agreement_2026-09-03.json`.

## Risultato per metrica

| Metrica | n | Kappa pesato (quadratico) | Interpretazione | α di Krippendorff | MAE | Media umano | Media giudice | Pearson r |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Fedeltà | 30 | **-0,019** | nessun accordo | -0,217 (inaffidabile) | 2,000 | 4,700 | 3,100 | -0,033 |
| Pertinenza | 30 | 0,770 | sostanziale | 0,774 (accettabile solo provvisorio) | 0,933 | 2,500 | 2,767 | 0,799 |
| Correttezza | 29 | 0,674 | sostanziale | 0,664 (inaffidabile) | 1,034 | 2,345 | 1,379 | 0,790 |

**Kappa medio: 0,475 ("moderato") — sotto la soglia di utilizzabilità dichiarata a monte (≥0,61).**

## Lettura

Il risultato non è uniforme fra le tre metriche, ed è proprio questa non
uniformità il dato rilevante:

- **Pertinenza e correttezza**: accordo sostanziale, giudice utilizzabile
  come *ordinamento* relativo delle risposte. Il giudice è però
  sistematicamente più severo dell'umano sulla correttezza (bias -0,966
  punti su scala 0-5): il numero assoluto riportato in `report_FINAL_V2.md`
  (correttezza media 1,33/5) va letto con questa calibrazione nota — la
  correttezza umana sulle stesse 30 domande è 2,345/5.
- **Fedeltà**: accordo sostanzialmente nullo. L'annotatore umano ha
  valutato fedeltà=5 in 28 domande su 30 (effetto soffitto), mentre il
  giudice automatico ha dato voti molto più dispersi (media 3,1). Coerente
  con l'ipotesi di self-preference bias (§11.5 di `doc/SISTEMA.md`): il
  giudice e il generatore sono lo stesso modello. **I punteggi di fedeltà
  del giudice automatico non vengono riportati come misura affidabile in
  questo lavoro.**

## Tassonomia degli errori — confronto fra metodo automatico e annotazione umana

| Stadio | Metodo automatico (rango + soglia, `report_FINAL_V2.md` §6.4) | Annotazione umana in cieco |
|---|---:|---:|
| retrieval_miss | 57% (17/30) | 46,7% (14/30) |
| ok | 20% (6/30) | 43,3% (13/30) |
| generation_miss | 20% (6/30) | 6,7% (2/30) |
| reranker_drop | 3% (1/30) | 3,3% (1/30) |

Le due decomposizioni concordano sul fatto qualitativo — il retrieval è la
causa dominante di errore, il reranker quasi irrilevante — ma divergono
sui numeri: il metodo automatico classifica più casi come `generation_miss`
e meno come `ok` rispetto al giudizio umano olistico. È un disaccordo
informativo: una soglia numerica rigida è meno indulgente di un lettore
umano nel decidere se una risposta "ha funzionato".

## Conclusione

Il giudice automatico **non è validato indistintamente**: è utilizzabile
per pertinenza e correttezza (con la calibrazione nota), non per fedeltà.
Riportare un punteggio di fedeltà automatico non validato avrebbe dato un
numero apparentemente "buono" (3,1/5) senza che nessuno potesse distinguere
una misura reale da un artefatto del bias di self-preference — è
esattamente il rischio che l'annotazione umana in cieco è stata introdotta
per controllare.
