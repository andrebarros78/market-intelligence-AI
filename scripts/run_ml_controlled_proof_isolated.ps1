$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$ExpectedAppId = "3438551912770538"
$ContainerName = "market-intelligence-pr70-postgres"
$DbPort = 55433
$WebhookPort = 8773
$WebhookPath = "/v1/webhooks/mercadolivre"
$WebhookStableTarget = "http://127.0.0.1:8772$WebhookPath"
$WebhookIsolatedTarget = "http://127.0.0.1:$WebhookPort$WebhookPath"
$WebhookProcess = $null
$ContainerCreated = $false
$WebhookRouteSwitched = $false

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Dependencia ausente: $Name"
    }
}

function Wait-TcpPort([int]$Port, [int]$Attempts = 30) {
    for ($i = 0; $i -lt $Attempts; $i++) {
        $ok = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($ok) { return }
        Start-Sleep -Seconds 1
    }
    throw "Porta local $Port nao ficou pronta."
}

Assert-Command docker
Assert-Command python
Assert-Command tailscale

if (-not $env:MI_ML_APP_ID) { $env:MI_ML_APP_ID = $ExpectedAppId }
if ($env:MI_ML_APP_ID -ne $ExpectedAppId) { throw "MI_ML_APP_ID incorreto." }

$env:PYTHONPATH = "$Repo\src;$Repo"
$env:MI_READ_ONLY = "true"
$env:MI_ALLOW_MARKETPLACE_WRITES = "false"
$env:MI_CONTROLLED_WRITE_TEST_APPROVED = "pause-resume-1-item"

# Never touch the existing dedicated PostgreSQL on 55432. This recovery stack is
# intentionally parallel and disposable, so it does not require decrypting or
# rotating any pre-existing DPAPI-protected database credential.
$existing = (& docker ps -a --filter "name=^/$ContainerName$" --format "{{.ID}}" | Out-String).Trim()
if ($existing) {
    throw "Container isolado antigo encontrado ($ContainerName). Remova-o somente apos confirmar que nao ha prova em andamento."
}

$random = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($random)
$dbPassword = [Convert]::ToBase64String($random).TrimEnd('=').Replace('+','A').Replace('/','B')
$dbUser = "mi_pr70"
$dbName = "market_intelligence_pr70"
$encodedPassword = [Uri]::EscapeDataString($dbPassword)
$env:MI_DATABASE_URL = "postgresql://$dbUser`:$encodedPassword@127.0.0.1:$DbPort/$dbName"
$env:TEST_DATABASE_URL = $env:MI_DATABASE_URL

try {
    Write-Host "ISOLATED_POSTGRES_PORT=$DbPort"
    & docker run -d --name $ContainerName `
        -e "POSTGRES_USER=$dbUser" `
        -e "POSTGRES_PASSWORD=$dbPassword" `
        -e "POSTGRES_DB=$dbName" `
        -p "127.0.0.1:$DbPort`:5432" `
        postgres:17-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar PostgreSQL isolado." }
    $ContainerCreated = $true

    for ($i = 0; $i -lt 30; $i++) {
        & docker exec $ContainerName pg_isready -U $dbUser -d $dbName | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    & docker exec $ContainerName pg_isready -U $dbUser -d $dbName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL isolado nao ficou pronto." }
    Write-Host "DATABASE_CONNECTION=PORT_READY"

    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic upgrade head falhou." }

    python -c "import os, psycopg; c=psycopg.connect(os.environ['MI_DATABASE_URL']); cur=c.cursor(); cur.execute('select 1'); assert cur.fetchone()[0] == 1; cur.execute('select version_num from alembic_version'); print('ALEMBIC_HEAD=' + cur.fetchone()[0]); c.close()"
    if ($LASTEXITCODE -ne 0) { throw "Validacao SQL do PostgreSQL isolado falhou." }
    Write-Host "DATABASE_CONNECTION=PROVEN"

    $env:MI_ML_WEBHOOK_LOCAL_PORT = "$WebhookPort"
    $WebhookProcess = Start-Process -FilePath "python" -ArgumentList "scripts/run_mercadolivre_webhooks.py" -WorkingDirectory $Repo -PassThru -WindowStyle Hidden
    Wait-TcpPort -Port $WebhookPort
    Write-Host "WEBHOOK_LOCAL_ISOLATED=PROVEN"

    & tailscale funnel --yes --bg --https=443 --set-path=$WebhookPath $WebhookIsolatedTarget | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Falha ao apontar webhook publico para runtime isolado." }
    $WebhookRouteSwitched = $true

    $status = (& tailscale funnel status 2>&1 | Out-String)
    if ($status -notmatch [regex]::Escape($WebhookPath) -or $status -notmatch [regex]::Escape("127.0.0.1:$WebhookPort")) {
        throw "Rota publica do webhook isolado nao foi confirmada no Tailscale Funnel."
    }
    Write-Host "WEBHOOK_PUBLIC_ROUTE_ISOLATED=PROVEN"

    & "$PSScriptRoot\run_ml_controlled_oauth_and_proof.ps1"
    $proofCode = $LASTEXITCODE
    Write-Host "ISOLATED_PR70_EXIT_CODE=$proofCode"
    if ($proofCode -ne 0) { exit $proofCode }
}
finally {
    Remove-Item Env:MI_ML_WEBHOOK_LOCAL_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MI_DATABASE_URL -ErrorAction SilentlyContinue
    $dbPassword = $null
    $encodedPassword = $null

    if ($WebhookRouteSwitched) {
        & tailscale funnel --yes --bg --https=443 --set-path=$WebhookPath $WebhookStableTarget | Out-Null
        Write-Host "WEBHOOK_PUBLIC_ROUTE_RESTORED=True"
    }

    if ($WebhookProcess -and -not $WebhookProcess.HasExited) {
        Stop-Process -Id $WebhookProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "ISOLATED_WEBHOOK_STOPPED=True"
    }

    if ($ContainerCreated) {
        & docker rm -f $ContainerName | Out-Null
        Write-Host "ISOLATED_POSTGRES_REMOVED=True"
    }
}
