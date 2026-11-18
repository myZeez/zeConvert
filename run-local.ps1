$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Virtual environment belum ada. Ikuti bagian Instalasi Windows di README.md terlebih dahulu.'
}
$port = if ($env:PORT) { $env:PORT } else { '8001' }
Write-Output "Buka http://127.0.0.1:$port setelah server siap."
& $python -m uvicorn backend.main:app --host 127.0.0.1 --port $port
