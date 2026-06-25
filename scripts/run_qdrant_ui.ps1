param([switch]$Help)
if ($Help) {
    Write-Host "Avvia Qdrant Explorer (Streamlit UI per i documenti indicizzati)"
    Write-Host "USO: .\scripts\run_qdrant_ui.ps1"
    exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

.\.venv\Scripts\Activate.ps1
Write-Host "[Qdrant Explorer] http://localhost:8501" -ForegroundColor Cyan
streamlit run scripts/qdrant_explorer.py
