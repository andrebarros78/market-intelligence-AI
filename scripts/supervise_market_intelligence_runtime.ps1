$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $Repo "runtime"
$ConfigRoot = Join-Path $RuntimeRoot "config"
$SecretPath = Join-Path $ConfigRoot "database-url.dpapi"
$SupervisorRoot = Join-Path $RuntimeRoot "supervisor"
$SupervisorStatus = Join-Path $SupervisorRoot "status.json"
$RadarStatus = Join-Path $RuntimeRoot "radar-unit\status.json"
$Python = "C:\Python313\pythonw.exe"
$Postgres = "C:\Program Files\PostgreSQL\17\bin\postgres.exe"
$PostgresData = "C:\Users\andre\AppData\Local\MarketIntelligence\PostgreSQL17\data"
$PostgresLogRoot = "C:\Users\andre\AppData\Local\MarketIntelligence\PostgreSQL17"
$AppId = "3438551912770538"

New-Item -ItemType Directory -Force -Path $SupervisorRoot | Out-Null
if (-not (Test-Path $SecretPath)) { throw "Encrypted database URL not provisioned." }
if (-not (Test-Path $Python)) { throw "Python runtime not found." }
if (-not (Test-Path $Postgres)) { throw "PostgreSQL runtime not found." }
if (-not (Test-Path $PostgresData)) { throw "PostgreSQL data directory not found." }

function Test-ListeningPort([int]$Port) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Get-DatabaseUrl {
    $secure = (Get-Content -Raw -Path $SecretPath).Trim() | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    }
}

function Set-ChildEnvironment([string]$DatabaseUrl) {
    $env:PYTHONPATH = Join-Path $Repo "src"
    $env:MI_DATABASE_URL = $DatabaseUrl
    $env:MI_ML_APP_ID = $AppId
    $env:MI_READ_ONLY = "true"
    $env:MI_ALLOW_MARKETPLACE_WRITES = "false"
}

function Clear-DatabaseEnvironment {
    Remove-Item Env:MI_DATABASE_URL -ErrorAction SilentlyContinue
}

function Start-PermanentPostgres {
    if (Test-ListeningPort 55432) { return }
    Start-Process -FilePath $Postgres `
        -ArgumentList @("-D", ('"{0}"' -f $PostgresData)) `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PostgresLogRoot "postgres-supervisor.stdout.log") `
        -RedirectStandardError (Join-Path $PostgresLogRoot "postgres-supervisor.stderr.log") | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-ListeningPort 55432) { return }
        Start-Sleep -Seconds 1
    }
    throw "PostgreSQL 55432 did not become ready."
}

function Test-WebhookHealth {
    if (-not (Test-ListeningPort 8772)) { return $false }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8772/health" -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Start-PermanentWebhook([string]$DatabaseUrl) {
    if (Test-WebhookHealth) { return }
    if (Test-ListeningPort 8772) { return }
    Set-ChildEnvironment $DatabaseUrl
    $env:MI_ML_WEBHOOK_LOCAL_PORT = "8772"
    try {
        $webhookScript = Join-Path $Repo "scripts\run_mercadolivre_webhooks.py"
        Start-Process -FilePath $Python `
            -ArgumentList ('"{0}"' -f $webhookScript) `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $PostgresLogRoot "webhook-supervisor.stdout.log") `
            -RedirectStandardError (Join-Path $PostgresLogRoot "webhook-supervisor.stderr.log") | Out-Null
    }
    finally {
        Remove-Item Env:MI_ML_WEBHOOK_LOCAL_PORT -ErrorAction SilentlyContinue
        Clear-DatabaseEnvironment
    }
}

function Get-RadarUnitProcess {
    return Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*run_radar_sovereign_unit.py*" } |
        Select-Object -First 1
}

function Start-RadarUnit([string]$DatabaseUrl) {
    if (Get-RadarUnitProcess) { return }
    Set-ChildEnvironment $DatabaseUrl
    try {
        $radarScript = Join-Path $Repo "scripts\run_radar_sovereign_unit.py"
        $radarArgs = ('"{0}" --status-path "{1}" --interval-seconds 30' -f $radarScript, $RadarStatus)
        Start-Process -FilePath $Python `
            -ArgumentList $radarArgs `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $SupervisorRoot "radar.stdout.log") `
            -RedirectStandardError (Join-Path $SupervisorRoot "radar.stderr.log") | Out-Null
    }
    finally { Clear-DatabaseEnvironment }
}

function Write-SupervisorStatus([hashtable]$Status) {
    $Status.timestamp = [DateTimeOffset]::UtcNow.ToString("o")
    $Status.MI_READ_ONLY = $true
    $Status.MI_ALLOW_MARKETPLACE_WRITES = $false
    $Status.operational_horizon_years = 5000
    $Status.lifecycle = "always_on"
    $Status.unit_classification = "sovereign_universal_unit"
    $Status.runtime_scope = "universal_multimarketplace"
    $Status.restart_policy = "always"
    $temp = "$SupervisorStatus.tmp"
    $Status | ConvertTo-Json -Depth 5 | Set-Content -Path $temp -Encoding utf8
    Move-Item -Force -Path $temp -Destination $SupervisorStatus
}

while ($true) {
    try {
        Start-PermanentPostgres
        $db = Get-DatabaseUrl
        try {
            Start-PermanentWebhook $db
            Start-RadarUnit $db
        }
        finally { $db = $null; Clear-DatabaseEnvironment }

        $radarProcess = Get-RadarUnitProcess
        Write-SupervisorStatus @{
            supervisor = "ACTIVE"
            postgres_55432 = (Test-ListeningPort 55432)
            webhook_8772 = (Test-WebhookHealth)
            radar_unit_process = ($null -ne $radarProcess)
            radar_unit_pid = if ($radarProcess) { [int]$radarProcess.ProcessId } else { $null }
            new_marketplace_write_executed = $false
        }
    }
    catch {
        Write-SupervisorStatus @{
            supervisor = "DEGRADED_RETRYING"
            postgres_55432 = (Test-ListeningPort 55432)
            webhook_8772 = (Test-WebhookHealth)
            radar_unit_process = ($null -ne (Get-RadarUnitProcess))
            error = $_.Exception.GetType().Name
            new_marketplace_write_executed = $false
        }
    }
    Start-Sleep -Seconds 15
}
