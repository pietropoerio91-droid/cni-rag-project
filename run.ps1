param(
    [switch]$SetupOnly,
    [switch]$ApiOnly,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Show-Help {
    Write-Host @"
CNI RAG - Script di avvio
==========================

USO:
  .\run.ps1                    # Setup + ingestion + API + frontend
  .\run.ps1 -SetupOnly         # Solo attiva venv e installa dip
  .\run.ps1 -ApiOnly           # Solo avvia API server

PREREQUISITI:
  - Docker con Qdrant in esecuzione (oppure QDRANT_MODE=local)
  - LM Studio con Llama 3.2 su http://localhost:1234
  - Node.js 20+ (per frontend)

PULSANTI VS CODE (F5):
  - "Avvia API Server"
  - "Crawl + Ingest (completo)"
  - "Solo indicizzazione (no crawl)"
  - "Solo crawler"
  - "Ricostruisci indice"
"@
    exit 0
}

if ($Help) { Show-Help }

# --- Step 0: Verifica prerequisites ---
Write-Host "`n[1/6] Verifica ambiente..." -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "  Creazione virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

.venv\Scripts\Activate.ps1

# --- Step 1: Installa dipendenze ---
Write-Host "[2/6] Installazione dipendenze Python..." -ForegroundColor Cyan
pip install -r requirements.txt -q

# --- Step 2: Copia .env se mancante ---
if (-not (Test-Path ".env")) {
    Write-Host "[3/6] Creazione .env da .env.example..." -ForegroundColor Cyan
    Copy-Item .env.example .env
} else {
    Write-Host "[3/6] .env già esistente, skip" -ForegroundColor Cyan
}

if ($SetupOnly) {
    Write-Host "[green]Setup completato! Il venv è attivo.`n" -ForegroundColor Green
    exit 0
}

# --- Step 3: Ingestione (solo se non già indicizzato) ---
$indexed = $false
if (Test-Path "data/qdrant_db") {
    $files = Get-ChildItem "data/qdrant_db" -Recurse -File
    if ($files.Count -gt 0) { $indexed = $true }
}

if (-not $indexed) {
    Write-Host "[4/6] Esecuzione ingestion pipeline..." -ForegroundColor Cyan
    python scripts/run_ingestion.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Ingestion fallita. Controlla gli errori sopra." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[4/6] Dati già indicizzati, skip ingestion" -ForegroundColor Cyan
}

# --- Step 4: Avvia API ---
Write-Host "[5/6] Avvio API server su http://localhost:8000..." -ForegroundColor Cyan
$apiJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    .venv\Scripts\Activate.ps1
    python scripts/run_api.py
} -ArgumentList $ScriptDir

Start-Sleep -Seconds 3

if ($ApiOnly) {
    Write-Host "`nAPI server in esecuzione su http://localhost:8000" -ForegroundColor Green
    Write-Host "Premi Ctrl+C per fermarlo.`n" -ForegroundColor Yellow
    Receive-Job $apiJob
    Wait-Job $apiJob
    exit 0
}

# --- Step 5: Avvia frontend ---
Write-Host "[6/6] Avvio frontend Angular..." -ForegroundColor Cyan

if (Test-Path "frontend/node_modules") {
    Write-Host "  node_modules trovato, skip npm install" -ForegroundColor Gray
} else {
    Write-Host "  npm install in corso..." -ForegroundColor Yellow
    Set-Location frontend
    npm install
    Set-Location $ScriptDir
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Sistema avviato!" -ForegroundColor Green
Write-Host "  API:         http://localhost:8000" -ForegroundColor Green
Write-Host "  Frontend:    http://localhost:4200" -ForegroundColor Green
Write-Host "  Qdrant:      http://localhost:8000/qdrant" -ForegroundColor Green
Write-Host "  Docs API:    http://localhost:8000/docs" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Premi Ctrl+C per fermare tutto.`n" -ForegroundColor Yellow

# Avvia frontend, Qdrant UI e API in parallelo
$frontendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location "$dir/frontend"
    ng serve
} -ArgumentList $ScriptDir

# Aspetta che un job finisca (Ctrl+C)
Wait-Job $apiJob, $frontendJob

Stop-Job $apiJob, $frontendJob
Remove-Job $apiJob, $frontendJob

Write-Host "`nSistema fermato." -ForegroundColor Gray
