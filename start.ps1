param([ValidateSet('live','mock','configured')][string]$Mode='configured')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is already in use. If Signal is running, open http://localhost:8000/docs; otherwise stop the owning application.'
}
New-Item -ItemType Directory -Path 'data' -Force | Out-Null
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
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$api=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','marketing.api:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/api.log' -RedirectStandardError 'data/api-error.log'
$worker=Start-Process -FilePath $python -ArgumentList @('-m','marketing.worker') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/worker.log' -RedirectStandardError 'data/worker-error.log'
@{api=$api.Id;worker=$worker.Id;python=$python} | ConvertTo-Json | Set-Content -LiteralPath 'data/processes.json'
$deadline=(Get-Date).AddSeconds(30)
$ready=$false
while ((Get-Date) -lt $deadline) {
    $api.Refresh()
    $worker.Refresh()
    if ($api.HasExited -or $worker.HasExited) {
        & (Join-Path $PSScriptRoot 'stop.ps1')
        throw 'Startup failed. Check data/api-error.log and data/worker-error.log.'
    }
    try {
        $health=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
        $docs=Invoke-WebRequest -Uri 'http://127.0.0.1:8000/docs' -UseBasicParsing -TimeoutSec 2
        if ($health.ok -and $docs.StatusCode -eq 200) {$ready=$true; break}
    } catch { }
    Start-Sleep -Milliseconds 300
}
if (-not $ready) {
    & (Join-Path $PSScriptRoot 'stop.ps1')
    throw 'Startup timed out. Check data/api-error.log and data/worker-error.log.'
}
Write-Host 'Signal is ready: http://localhost:8000'
Write-Host 'API documentation: http://localhost:8000/docs'
Write-Host 'Create an account in the browser. Use ./stop.ps1 to stop these processes.'
