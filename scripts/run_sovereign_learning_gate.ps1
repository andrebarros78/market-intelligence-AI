$ErrorActionPreference = 'Stop'

$env:MI_READ_ONLY = 'true'
$env:MI_ALLOW_MARKETPLACE_WRITES = 'false'

$python = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { throw 'Python não encontrado' }

& $python scripts/run_sovereign_learning_gate.py
$code = $LASTEXITCODE
if ($code -ne 0) {
    throw "Sovereign learning gate falhou com código $code"
}

Write-Host 'RADAR_UNIVERSAL_SOBERANO_MCL_GATE=PASS'
