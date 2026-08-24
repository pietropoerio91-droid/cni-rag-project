#!/usr/bin/env bash
# Riavvio robusto dell'API CNI RAG.
# Uso: bash scripts/restart_api.sh [--wait]
#   --wait : attende che l'API risponda su /health prima di uscire
set -u
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
LOG="${LOG:-logs/api.log}"

# 1. Kill forzato (SIGTERM non basta: l'event loop puo' essere bloccato da una query)
PIDS=$(pgrep -f "run_api.py" || true)
if [ -n "$PIDS" ]; then
  echo "Termino API esistente: $PIDS"
  kill -9 $PIDS 2>/dev/null
fi

# 2. Attendo che porta e lock si liberino
for i in $(seq 1 15); do
  if ! lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 \
     && ! lsof data/qdrant_db/collection/cni_documents/storage.sqlite >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# 3. Avvio
mkdir -p logs
nohup "$PY" scripts/run_api.py --no-reload < /dev/null > "$LOG" 2>&1 &
disown
echo "API avviata (PID $!)"

# 4. Health check opzionale
if [ "${1:-}" = "--wait" ]; then
  for i in $(seq 1 36); do
    H=$(curl -s -m 3 http://localhost:8000/api/v1/health 2>/dev/null || true)
    if [ -n "$H" ]; then echo "READY dopo $((i*5))s: $H"; exit 0; fi
    sleep 5
  done
  echo "ERRORE: API non rispondente entro 180s" >&2
  tail -20 "$LOG" >&2
  exit 1
fi
