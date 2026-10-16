$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

if (-not (Test-Path (Join-Path $backend '.venv'))) {
    python -m venv (Join-Path $backend '.venv')
}

& (Join-Path $backend '.venv\Scripts\python.exe') -m pip install -r (Join-Path $backend 'requirements.txt')
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Push-Location $frontend
    npm install
    Pop-Location
}

Write-Host 'Starting backend on all network interfaces (port 8000)'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Write-Host 'Starting frontend on all network interfaces (port 5173)'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$frontend'; npm.cmd run dev -- --host 0.0.0.0 --port 5173"
