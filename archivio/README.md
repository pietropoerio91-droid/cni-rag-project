# Archivio — file superati, da cancellare

Copie *as is* di file non più allineati alla versione finale su `main`
(23/09/2026). Nessun file del progetto le usa o le cita: si possono
cancellare in blocco (`git rm -r archivio`) quando non servono più.

| File | Cos'era | Perché è qui |
|---|---|---|
| `CONCLUSIONI_TESI_2026-09-03.md` | appunti per le conclusioni, versione del 03/09 | numeri di `FINAL_V2`; la versione aggiornata a `FINAL_V3` è in `doc/CONCLUSIONI_TESI.md` |
| `INDICE_TESI-1.md` | copia dell'indice della tesi a 8 capitoli (16/09) | superato da `doc/INDICE_TESI.md` (6 capitoli, con `FINAL_V3`) |
| `anchored_summary.md` | riepilogo di una vecchia sessione di lavoro | descrive uno stato superato (embedding `paraphrase-multilingual` a 768 dimensioni, indice vuoto) |
| `docker/` | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | il sistema gira in locale senza Docker (Qdrant in modalità locale); il compose avviava anche un server Qdrant che il sistema non usa |
