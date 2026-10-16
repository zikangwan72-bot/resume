$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$backendOut = Join-Path $backend 'uvicorn.restart.stdout.log'
$backendErr = Join-Path $backend 'uvicorn.restart.stderr.log'
$frontendOut = Join-Path $frontend 'vite.restart.stdout.log'
$frontendErr = Join-Path $frontend 'vite.restart.stderr.log'

foreach ($port in 5173, 8000) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Milliseconds 500

Start-Process -FilePath $python `
    -ArgumentList '-m uvicorn app.main:app --host 0.0.0.0 --port 8000' `
    -WorkingDirectory $backend `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -WindowStyle Hidden

Start-Process -FilePath $npm `
    -ArgumentList 'run dev -- --host 0.0.0.0 --port 5173' `
    -WorkingDirectory $frontend `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -WindowStyle Hidden

$healthy = $false
for ($attempt = 1; $attempt -le 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $frontendStatus = (Invoke-WebRequest 'http://127.0.0.1:5173/dashboard' -UseBasicParsing).StatusCode
        $backendStatus = (Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health').data.status
        if ($frontendStatus -eq 200 -and $backendStatus -eq 'healthy') {
            $healthy = $true
            break
        }
    }
    catch {
        continue
    }
}

if (-not $healthy) {
    throw 'Project startup timed out. Check ports 5173 and 8000.'
}

Write-Host 'Enterprise AI Suite restarted.'
Write-Host 'Frontend: http://127.0.0.1:5173/dashboard'
Write-Host 'Backend: http://127.0.0.1:8000/api/v1/health'
