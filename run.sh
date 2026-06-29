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

# Step 2: Installa dipendenze
echo "[2/5] Installazione dipendenze Python..."
pip install -r requirements.txt -q

# Step 3: Copia .env se mancante
if [ ! -f ".env" ]; then
    echo "[3/5] Creazione .env da .env.example..."
    cp .env.example .env
else
    echo "[3/5] .env già esistente, skip"
fi

# Step 4: Ingestion se non già indicizzato
INDEXED=false
if [ -d "data/qdrant_db" ] && [ "$(ls -A data/qdrant_db 2>/dev/null)" ]; then
    INDEXED=true
fi

if [ "$INDEXED" = false ]; then
    echo "[4/5] Esecuzione ingestion pipeline..."
    python scripts/run_ingestion.py --max-pages 100
else
    echo "[4/5] Dati già indicizzati, skip ingestion"
fi

# Step 5: Avvia API + frontend
echo "[5/5] Avvio servizi..."

# Avvia API in background
echo "  Avvio API su http://localhost:8000..."
python scripts/run_api.py &
API_PID=$!

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
