$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath 'data/processes.json')) {Write-Host 'No recorded processes.'; exit}
$record=Get-Content -LiteralPath 'data/processes.json' -Raw | ConvertFrom-Json
foreach ($processId in @($record.api,$record.worker)) {
    $process=Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and $process.Path -eq $record.python) {Stop-Process -Id $processId}
}
Remove-Item -LiteralPath 'data/processes.json'
Write-Host 'Recorded project processes stopped.'
