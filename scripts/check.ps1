$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $root 'backend')
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Pop-Location

Push-Location (Join-Path $root 'frontend')
npm run typecheck
npm run build
npm run test:e2e
Pop-Location
