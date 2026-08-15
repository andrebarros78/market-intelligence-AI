$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$ExpectedAppId = "3438551912770538"
$ExpectedRedirectUri = "https://vendas.tail7ad8aa.ts.net/v1/oauth/mercadolivre/callback"

if (-not $env:MI_ML_APP_ID) { $env:MI_ML_APP_ID = $ExpectedAppId }
if ($env:MI_ML_APP_ID -ne $ExpectedAppId) { throw "MI_ML_APP_ID incorreto." }
if (-not $env:MI_ML_REDIRECT_URI) { $env:MI_ML_REDIRECT_URI = $ExpectedRedirectUri }
if ($env:MI_ML_REDIRECT_URI -ne $ExpectedRedirectUri) { throw "MI_ML_REDIRECT_URI diverge do callback registrado aprovado." }

# Do not depend on the current PowerShell process for the PostgreSQL connection.
# Prefer the current process when explicitly supplied, then persistent User/Machine scopes.
if (-not $env:MI_DATABASE_URL) {
    $persistentDbUrl = [Environment]::GetEnvironmentVariable("MI_DATABASE_URL", "User")
    if (-not $persistentDbUrl) {
        $persistentDbUrl = [Environment]::GetEnvironmentVariable("MI_DATABASE_URL", "Machine")
    }
    if ($persistentDbUrl) {
        $env:MI_DATABASE_URL = $persistentDbUrl
        Write-Host "MI_DATABASE_URL_LOADED_FROM_WINDOWS=True"
    }
}
if (-not $env:MI_DATABASE_URL) {
    throw "MI_DATABASE_URL ausente. Nenhuma conexao foi encontrada nos escopos Process/User/Machine do Windows."
}

$env:PYTHONPATH = "$Repo\src;$Repo"
$env:MI_CONTROLLED_WRITE_TEST_APPROVED = "pause-resume-1-item"
$env:MI_READ_ONLY = "true"
$env:MI_ALLOW_MARKETPLACE_WRITES = "false"

$redirect = [Uri]$env:MI_ML_REDIRECT_URI
$callbackPath = $redirect.AbsolutePath
if ([string]::IsNullOrWhiteSpace($callbackPath)) { $callbackPath = "/" }

$tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
$funnelStarted = $false

try {
    if ($tailscale) {
        Write-Host "OAUTH_FUNNEL_PATH=$callbackPath"
        # Tailscale mounts the public path and proxies to the target path. Preserve the
        # callback path explicitly on the local target so the OAuth handler receives the
        # exact registered URI instead of '/'.
        $localTarget = "http://127.0.0.1:8771$callbackPath"
        & tailscale funnel --yes --bg --https=443 --set-path=$callbackPath $localTarget | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Falha ao publicar callback OAuth temporario via Tailscale Funnel." }
        $funnelStarted = $true

        $status = (& tailscale funnel status 2>&1 | Out-String)
        Write-Host $status
        if ($status -notmatch [regex]::Escape($callbackPath)) {
            throw "Callback OAuth nao apareceu no status do Tailscale Funnel."
        }
    }
    else {
        Write-Host "TAILSCALE_CLI_NOT_FOUND=True"
        Write-Host "Usando rota HTTPS existente configurada em MI_ML_REDIRECT_URI."
    }

    Write-Host "=== OAUTH CONTROLADO ==="
    python scripts/ml_controlled_oauth_vault.py
    if ($LASTEXITCODE -ne 0) { throw "OAuth controlado falhou." }
}
finally {
    if ($funnelStarted) {
        & tailscale funnel --https=443 --set-path=$callbackPath off | Out-Null
        Write-Host "OAUTH_FUNNEL_REMOVED=True"
    }
}

Write-Host "=== PROVA REAL PR70 ==="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run_ml_controlled_proof_from_windows_vault.ps1"
$code = $LASTEXITCODE

Write-Host "PR70_EXIT_CODE=$code"
exit $code
