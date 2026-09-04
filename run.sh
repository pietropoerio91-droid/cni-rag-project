#!/bin/bash
# CNI RAG - Script di avvio per macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "  CNI RAG - Avvio (macOS)"
echo "========================================"
echo ""

# Step 1: Verifica ambiente
echo "[1/5] Verifica ambiente..."
if [ ! -d ".venv" ]; then
    echo "  Creazione virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# Step 2: Verifica Node.js
NODE_PATH="/tmp/node-v20.12.0-darwin-x64/bin"
if [ ! -f "$NODE_PATH/node" ]; then
    echo "  Node.js non trovato in /tmp/, scarico..."
    curl -fsSL https://nodejs.org/dist/v20.12.0/node-v20.12.0-darwin-x64.tar.gz | tar -xz -C /tmp/
fi
export PATH="$NODE_PATH:$PATH"

# Step 3: Copia .env se mancante
if [ ! -f ".env" ]; then
    echo "[2/5] Creazione .env da .env.example..."
    cp .env.example .env
else
    echo "[2/5] .env già esistente, skip"
fi

# Step 4: Ingestion se non già indicizzato
INDEXED=false
if [ -d "data/qdrant_db" ] && [ "$(ls -A data/qdrant_db 2>/dev/null)" ]; then
    INDEXED=true
fi

if [ "$INDEXED" = false ]; then
    echo "[3/5] Esecuzione ingestion pipeline..."
    python scripts/run_ingestion.py --max-pages 100
else
    echo "[3/5] Dati già indicizzati (17098 chunk), skip ingestion"
fi

# Step 5: Avvia API + frontend
echo "[4/5] Avvio servizi..."

# Ferma eventuali processi precedenti
kill $(lsof -t -i :8000) 2>/dev/null || true
kill $(lsof -t -i :4200) 2>/dev/null || true
sleep 1

# Avvia API in background (--no-reload per evitare processi zombie)
echo "  Avvio API su http://localhost:8000..."
python scripts/run_api.py --no-reload &
API_PID=$!

sleep 3

# Avvia frontend
echo "  Avvio frontend su http://localhost:4200..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "  npm install in corso..."
    npm install
fi
./node_modules/.bin/ng serve --port 4200 &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "  Sistema avviato!"
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:4200"
echo "  Docs API: http://localhost:8000/docs"
echo "========================================"
echo "  Premi Ctrl+C per fermare tutto."
echo ""

trap "kill $API_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
