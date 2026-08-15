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
$RuntimeRoot = Join-Path $Repo "runtime\isolated-pr70-stack"
$NativeDataDir = Join-Path $RuntimeRoot "pgdata"
$NativeLog = Join-Path $RuntimeRoot "postgres.log"
$WebhookProcess = $null
$ContainerCreated = $false
$NativePostgresStarted = $false
$NativePostgresProcess = $null
$WebhookRouteSwitched = $false
$PgCtl = $null
$PgIsReady = $null
$InitDb = $null

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

function Find-PostgresTool([string]$Tool) {
    $cmd = Get-Command $Tool -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $roots = @(
        "C:\Program Files\PostgreSQL\17\bin",
        "C:\Program Files\PostgreSQL\16\bin",
        "C:\Program Files\PostgreSQL\15\bin"
    )
    foreach ($root in $roots) {
        $candidate = Join-Path $root ("$Tool.exe")
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

Assert-Command python
Assert-Command tailscale

if (-not $env:MI_ML_APP_ID) { $env:MI_ML_APP_ID = $ExpectedAppId }
if ($env:MI_ML_APP_ID -ne $ExpectedAppId) { throw "MI_ML_APP_ID incorreto." }

$env:PYTHONPATH = "$Repo\src;$Repo"
$env:MI_READ_ONLY = "true"
$env:MI_ALLOW_MARKETPLACE_WRITES = "false"
$env:MI_CONTROLLED_WRITE_TEST_APPROVED = "pause-resume-1-item"

if (Test-NetConnection -ComputerName 127.0.0.1 -Port $DbPort -InformationLevel Quiet -WarningAction SilentlyContinue) {
    throw "Porta isolada $DbPort ja esta em uso. Nenhum processo existente sera alterado automaticamente."
}
if (Test-NetConnection -ComputerName 127.0.0.1 -Port $WebhookPort -InformationLevel Quiet -WarningAction SilentlyContinue) {
    throw "Porta isolada $WebhookPort ja esta em uso. Nenhum processo existente sera alterado automaticamente."
}

# This stack never touches the existing PostgreSQL on 55432 or webhook on 8772.
# A fresh password lives only in this PowerShell process and the temporary isolated
# database runtime, eliminating any need to decrypt or rotate pre-existing DPAPI data.
$random = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); try { $rng.GetBytes($random) } finally { $rng.Dispose() }
$dbPassword = [Convert]::ToBase64String($random).TrimEnd('=').Replace('+','A').Replace('/','B')
$dbUser = "mi_pr70"
$dbName = "postgres"
$encodedPassword = [Uri]::EscapeDataString($dbPassword)
$env:MI_DATABASE_URL = "postgresql://$dbUser`:$encodedPassword@127.0.0.1:$DbPort/$dbName"
$env:TEST_DATABASE_URL = $env:MI_DATABASE_URL

$docker = Get-Command docker -ErrorAction SilentlyContinue
$useDocker = $false
if ($docker) {
    & docker info *> $null
    $useDocker = ($LASTEXITCODE -eq 0)
}

try {
    Write-Host "ISOLATED_POSTGRES_PORT=$DbPort"

    if ($useDocker) {
        $existing = (& docker ps -a --filter "name=^/$ContainerName$" --format "{{.ID}}" | Out-String).Trim()
        if ($existing) {
            throw "Container isolado antigo encontrado ($ContainerName). Nenhum container preexistente sera removido automaticamente."
        }

        & docker run -d --name $ContainerName `
            -e "POSTGRES_USER=$dbUser" `
            -e "POSTGRES_PASSWORD=$dbPassword" `
            -e "POSTGRES_DB=$dbName" `
            -p "127.0.0.1:$DbPort`:5432" `
            postgres:17-alpine | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criar PostgreSQL isolado via Docker." }
        $ContainerCreated = $true

        for ($i = 0; $i -lt 30; $i++) {
            & docker exec $ContainerName pg_isready -U $dbUser -d $dbName | Out-Null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 1
        }
        & docker exec $ContainerName pg_isready -U $dbUser -d $dbName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL isolado Docker nao ficou pronto." }
        Write-Host "ISOLATED_POSTGRES_ENGINE=Docker"
    }
    else {
        $InitDb = Find-PostgresTool "initdb"
        $PgCtl = Find-PostgresTool "pg_ctl"
        $PgIsReady = Find-PostgresTool "pg_isready"
        if (-not $InitDb -or -not $PgCtl -or -not $PgIsReady) {
            throw "Docker indisponivel e ferramentas nativas PostgreSQL (initdb/pg_ctl/pg_isready) nao foram encontradas."
        }
        if (Test-Path $RuntimeRoot) {
            throw "Runtime isolado antigo encontrado em $RuntimeRoot. Ele nao sera apagado automaticamente."
        }

        New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
        $pwFile = Join-Path $RuntimeRoot "pgpw.tmp"
        [IO.File]::WriteAllText($pwFile, $dbPassword, [Text.Encoding]::UTF8)
        try {
            & $InitDb -D $NativeDataDir -U $dbUser -A scram-sha-256 --pwfile=$pwFile --encoding=UTF8 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "initdb falhou para PostgreSQL isolado." }
        }
        finally {
            Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
        }

        Add-Content -Path (Join-Path $NativeDataDir "postgresql.conf") -Value "`nlisten_addresses = '127.0.0.1'`nport = $DbPort`n"
        $PostgresExe = Join-Path (Split-Path $PgCtl -Parent) "postgres.exe"
        if (-not (Test-Path $PostgresExe)) { throw "postgres.exe nao encontrado ao lado de pg_ctl." }
        $pgStdout = Join-Path $RuntimeRoot "postgres.stdout.log"
        $pgStderr = Join-Path $RuntimeRoot "postgres.stderr.log"
        $pgArgs = @("-D", ('"{0}"' -f $NativeDataDir))
        $NativePostgresProcess = Start-Process -FilePath $PostgresExe -ArgumentList $pgArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput $pgStdout -RedirectStandardError $pgStderr
        $NativePostgresStarted = $true

        for ($i = 0; $i -lt 30; $i++) {
            & $PgIsReady -h 127.0.0.1 -p $DbPort -U $dbUser -d $dbName | Out-Null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 1
        }
        & $PgIsReady -h 127.0.0.1 -p $DbPort -U $dbUser -d $dbName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL isolado nativo nao ficou pronto." }
        Write-Host "ISOLATED_POSTGRES_ENGINE=Native"
    }

    Write-Host "DATABASE_CONNECTION=PORT_READY"

    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic upgrade head falhou." }

    python -c "import os, psycopg; c=psycopg.connect(os.environ['MI_DATABASE_URL']); cur=c.cursor(); cur.execute('select 1'); assert cur.fetchone()[0] == 1; cur.execute('select version_num from alembic_version'); print('ALEMBIC_HEAD=' + cur.fetchone()[0]); c.close()"
    if ($LASTEXITCODE -ne 0) { throw "Validacao SQL do PostgreSQL isolado falhou." }
    Write-Host "DATABASE_CONNECTION=PROVEN"

    $env:MI_ML_WEBHOOK_LOCAL_PORT = "$WebhookPort"
    $WebhookProcess = Start-Process -FilePath "python" -ArgumentList "scripts/run_mercadolivre_webhooks.py" -WorkingDirectory $Repo -PassThru -WindowStyle Hidden
    Wait-TcpPort -Port $WebhookPort
    if ($WebhookProcess.HasExited) { throw "Webhook isolado encerrou durante bootstrap." }
    Write-Host "WEBHOOK_LOCAL_ISOLATED=PROVEN"

    & tailscale funnel --yes --bg --https=443 --set-path=$WebhookPath $WebhookIsolatedTarget | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Falha ao apontar webhook publico para runtime isolado." }
    $WebhookRouteSwitched = $true

    $status = (& tailscale funnel status 2>&1 | Out-String)
    if ($status -notmatch [regex]::Escape($WebhookPath) -or $status -notmatch [regex]::Escape("127.0.0.1:$WebhookPort")) {
        throw "Rota publica do webhook isolado nao foi confirmada no Tailscale Funnel."
    }
    Write-Host "WEBHOOK_PUBLIC_ROUTE_ISOLATED=PROVEN"

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run_ml_controlled_oauth_and_proof.ps1"
    $proofCode = $LASTEXITCODE
    Write-Host "ISOLATED_PR70_EXIT_CODE=$proofCode"
    if ($proofCode -ne 0) { throw "Prova PR70 encerrou com codigo $proofCode." }
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
    if ($NativePostgresStarted -and $NativePostgresProcess) {
        if (-not $NativePostgresProcess.HasExited) {
            & taskkill /PID $NativePostgresProcess.Id /T /F | Out-Null
        }
        Write-Host "ISOLATED_POSTGRES_STOPPED=True"
    }
    if (Test-Path $RuntimeRoot) {
        Remove-Item $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $RuntimeRoot)) { Write-Host "ISOLATED_POSTGRES_RUNTIME_REMOVED=True" }
    }
}
