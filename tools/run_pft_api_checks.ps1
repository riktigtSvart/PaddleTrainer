param([string]$PythonPath = "")
$ErrorActionPreference = "Stop"
$PftProjectRoot = Split-Path $PSScriptRoot -Parent
$PftApiRoot = Join-Path $PftProjectRoot "apps/api"
if ($PythonPath -eq "") {
    $PythonPath = Join-Path $PftProjectRoot ".venv/Scripts/python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Add meg a sajat API virtualis kornyezet PythonPath erteket."
}
$PftPython = (Resolve-Path -LiteralPath $PythonPath).Path
$PftPreviousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $PftApiRoot
    & $PftPython (Join-Path $PSScriptRoot "check_pft_api_integration.py")
    if ($LASTEXITCODE -ne 0) { throw "Az integracios ellenorzes nem sikerult; kuldd vissza a kimenetet." }
}
finally {
    $env:PYTHONPATH = $PftPreviousPythonPath
}
