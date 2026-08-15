$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $Repo "runtime"
$ConfigRoot = Join-Path $RuntimeRoot "config"
$SecretPath = Join-Path $ConfigRoot "database-url.dpapi"
$SupervisorRoot = Join-Path $RuntimeRoot "supervisor"
$SupervisorStatus = Join-Path $SupervisorRoot "status.json"
$RadarStatus = Join-Path $RuntimeRoot "radar-unit\status.json"
$SensorStatus = Join-Path $RuntimeRoot "sensors\status.json"
$CoreStatus = Join-Path $RuntimeRoot "sovereign-core\status.json"
$MissionTokenPath = Join-Path $ConfigRoot "mission-api-token.txt"
$Python = Join-Path $Repo ".venv-r113\Scripts\pythonw.exe"
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
    $env:MARKETPLACE_WRITES = "0"
}

function Clear-DatabaseEnvironment {
    Remove-Item Env:MI_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MARKETPLACE_WRITES -ErrorAction SilentlyContinue
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
    $expected = Join-Path $Repo "scripts\run_radar_sovereign_unit.py"
    return Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
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

function Get-SensorCollectorProcess {
    $expected = Join-Path $Repo "scripts\run_universal_sensor_collector.py"
    return Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
        Select-Object -First 1
}

function Start-SensorCollector([string]$DatabaseUrl) {
    if (Get-SensorCollectorProcess) { return }
    Set-ChildEnvironment $DatabaseUrl
    try {
        $sensorScript = Join-Path $Repo "scripts\run_universal_sensor_collector.py"
        $sensorArgs = ('"{0}" --status-path "{1}" --interval-seconds 300 --max-items-per-cycle 20' -f $sensorScript, $SensorStatus)
        Start-Process -FilePath $Python `
            -ArgumentList $sensorArgs `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $SupervisorRoot "sensor.stdout.log") `
            -RedirectStandardError (Join-Path $SupervisorRoot "sensor.stderr.log") | Out-Null
    }
    finally { Clear-DatabaseEnvironment }
}

function Get-SovereignCoreProcess {
    $expected = Join-Path $Repo "scripts\run_sovereign_intelligence_core.py"
    return Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
        Select-Object -First 1
}

function Start-SovereignCore([string]$DatabaseUrl) {
    if (Get-SovereignCoreProcess) { return }
    Set-ChildEnvironment $DatabaseUrl
    try {
        $coreScript = Join-Path $Repo "scripts\run_sovereign_intelligence_core.py"
        $coreArgs = ('"{0}" --status-path "{1}" --interval-seconds 60 --max-records 32' -f $coreScript, $CoreStatus)
        Start-Process -FilePath $Python `
            -ArgumentList $coreArgs `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $SupervisorRoot "sovereign-core.stdout.log") `
            -RedirectStandardError (Join-Path $SupervisorRoot "sovereign-core.stderr.log") | Out-Null
    }
    finally { Clear-DatabaseEnvironment }
}



function Get-MissionOrchestratorProcess {
    $expected = Join-Path $Repo "scripts\run_sovereign_mission_orchestrator.py"
    return Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
        Select-Object -First 1
}

function Start-MissionOrchestrator([string]$DatabaseUrl) {
    if (Get-MissionOrchestratorProcess) { return }
    Set-ChildEnvironment $DatabaseUrl
    try {
        $script = Join-Path $Repo "scripts\run_sovereign_mission_orchestrator.py"
        Start-Process -FilePath $Python `
            -ArgumentList ('"{0}" --host 127.0.0.1 --port 8785' -f $script) `
            -WorkingDirectory $Repo `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $SupervisorRoot "mission-orchestrator.stdout.log") `
            -RedirectStandardError (Join-Path $SupervisorRoot "mission-orchestrator.stderr.log") | Out-Null
    }
    finally { Clear-DatabaseEnvironment }
}

function Get-MissionHealth {
    if (-not (Test-ListeningPort 8785)) { return $null }
    if (-not (Test-Path $MissionTokenPath)) { return $null }
    try {
        $token = (Get-Content -Raw -Path $MissionTokenPath).Trim()
        return Invoke-RestMethod -Uri "http://127.0.0.1:8785/v1/mission-system/health" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 3
    }
    catch { return $null }
}

function Write-SupervisorStatus([hashtable]$Status) {
    $Status.timestamp = [DateTimeOffset]::UtcNow.ToString("o")
    $Status.MI_READ_ONLY = $true
    $Status.MI_ALLOW_MARKETPLACE_WRITES = $false
    $Status.MARKETPLACE_WRITES = 0
    $Status.operational_horizon_years = 5000
    $Status.lifecycle = "always_on"
    $Status.unit_classification = "sovereign_universal_unit"
    $Status.sovereign_core_classification = "sovereign_intelligence_counterintelligence_core"
    $Status.radar_is_subsystem = $true
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
            Start-SensorCollector $db
            Start-SovereignCore $db
            Start-MissionOrchestrator $db
        }
        finally { $db = $null; Clear-DatabaseEnvironment }

        $radarProcess = Get-RadarUnitProcess
        $sensorProcess = Get-SensorCollectorProcess
        $coreProcess = Get-SovereignCoreProcess
        $missionProcess = Get-MissionOrchestratorProcess
        $missionHealth = Get-MissionHealth
        Write-SupervisorStatus @{
            supervisor = "ACTIVE"
            postgres_55432 = (Test-ListeningPort 55432)
            webhook_8772 = (Test-WebhookHealth)
            radar_unit_process = ($null -ne $radarProcess)
            radar_unit_pid = if ($radarProcess) { [int]$radarProcess.ProcessId } else { $null }
            sensor_collector_process = ($null -ne $sensorProcess)
            sensor_collector_pid = if ($sensorProcess) { [int]$sensorProcess.ProcessId } else { $null }
            sovereign_core_process = ($null -ne $coreProcess)
            sovereign_core_pid = if ($coreProcess) { [int]$coreProcess.ProcessId } else { $null }
            mission_orchestrator_process = ($null -ne $missionProcess)
            mission_orchestrator_pid = if ($missionProcess) { [int]$missionProcess.ProcessId } else { $null }
            missions_running = if ($missionHealth) { [int]$missionHealth.missions_running } else { 0 }
            missions_pending = if ($missionHealth) { [int]$missionHealth.missions_pending } else { 0 }
            last_completed_mission = if ($missionHealth) { $missionHealth.last_completed_mission } else { $null }
            last_report_at = if ($missionHealth) { $missionHealth.last_report_at } else { $null }
            new_marketplace_write_executed = $false
        }
    }
    catch {
        Write-SupervisorStatus @{
            supervisor = "DEGRADED_RETRYING"
            postgres_55432 = (Test-ListeningPort 55432)
            webhook_8772 = (Test-WebhookHealth)
            radar_unit_process = ($null -ne (Get-RadarUnitProcess))
            sensor_collector_process = ($null -ne (Get-SensorCollectorProcess))
            sovereign_core_process = ($null -ne (Get-SovereignCoreProcess))
            mission_orchestrator_process = ($null -ne (Get-MissionOrchestratorProcess))
            error = $_.Exception.GetType().Name
            new_marketplace_write_executed = $false
        }
    }
    Start-Sleep -Seconds 15
}
