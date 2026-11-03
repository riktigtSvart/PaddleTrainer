$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$apiPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $apiPython)) { throw 'A projekt .venv Python ertelmezoje nem talalhato.' }

Push-Location (Join-Path $projectRoot 'apps\api')
try {
    & $apiPython -m pytest tests\planning\test_p2_4c18_planning_inputs.py tests\planning\test_p2_4c18_2_goal_suggestions.py tests\planning\test_p2_4c18_3_strategy.py tests\planning\test_p2_4c18_4_training_plan.py -q
    if ($LASTEXITCODE -ne 0) { throw 'A backend C18 tesztkapu sikertelen.' }
} finally { Pop-Location }

Push-Location (Join-Path $projectRoot 'apps\web')
try {
    & node.exe --test tests\training-plan.test.mjs tests\planning-inputs.test.mjs tests\planning-strategy.test.mjs
    if ($LASTEXITCODE -ne 0) { throw 'A frontend szerzodesteszt sikertelen.' }
    & node.exe node_modules\next\dist\bin\next typegen
    if ($LASTEXITCODE -ne 0) { throw 'A Next tipusgeneralas sikertelen.' }
    & node.exe node_modules\typescript\bin\tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw 'A TypeScript ellenorzes sikertelen.' }
    & node.exe node_modules\eslint\bin\eslint.js src\components\planning-cycles\training-plan.tsx src\lib\planning-cycles\training-plan.ts src\lib\planning-goals\proxy.ts
    if ($LASTEXITCODE -ne 0) { throw 'Az uj frontend kod lint ellenorzese sikertelen.' }
} finally { Pop-Location }
Write-Host 'C18.4 TESZTKAPU OK'
