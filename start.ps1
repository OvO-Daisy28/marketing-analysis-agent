param([ValidateSet('live','mock','configured')][string]$Mode='configured')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    (Get-Content -LiteralPath '.env' -Raw).Replace('postgresql+psycopg://marketing:marketing_local@localhost:5432/marketing','sqlite:///./data/local.db') | Set-Content -LiteralPath '.env' -Encoding utf8
}
if ($Mode -ne 'configured') {$env:MODEL_MODE=$Mode}
uv sync --frozen
if ($LASTEXITCODE -ne 0) {throw 'Dependency installation failed'}
uv run python -m marketing.cli init-db
if ($LASTEXITCODE -ne 0) {throw 'Database migration failed'}
uv run python -m marketing.cli import-data
if ($LASTEXITCODE -ne 0) {throw 'Data import failed'}
Push-Location web
try { npm ci; if ($LASTEXITCODE -ne 0) {throw 'npm ci failed'}; npm run build; if ($LASTEXITCODE -ne 0) {throw 'Web build failed'} } finally {Pop-Location}
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {throw 'Port 8000 is already in use; stop the existing process first.'}
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$api=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','marketing.api:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/api.log' -RedirectStandardError 'data/api-error.log'
$worker=Start-Process -FilePath $python -ArgumentList @('-m','marketing.worker') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/worker.log' -RedirectStandardError 'data/worker-error.log'
@{api=$api.Id;worker=$worker.Id;python=$python} | ConvertTo-Json | Set-Content -LiteralPath 'data/processes.json'
Write-Host 'Signal is starting: http://localhost:8000'
Write-Host 'Create an account in the browser. Use ./stop.ps1 to stop these processes.'
