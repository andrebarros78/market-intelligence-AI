$ErrorActionPreference = "Stop"

$PrimaryTask = "MarketIntelligenceAI-Radar-Skills-24x7"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SupervisorStatus = Join-Path $Repo "runtime\supervisor\status.json"
$MaxHeartbeatAgeSeconds = 90

function Get-HeartbeatAgeSeconds {
    if (-not (Test-Path $SupervisorStatus)) { return [double]::PositiveInfinity }
    try {
        $status = Get-Content -Raw -Path $SupervisorStatus | ConvertFrom-Json
        if (-not $status.timestamp) { return [double]::PositiveInfinity }
        $observed = [DateTimeOffset]::Parse([string]$status.timestamp)
        return ([DateTimeOffset]::UtcNow - $observed.ToUniversalTime()).TotalSeconds
    }
    catch { return [double]::PositiveInfinity }
}

$task = Get-ScheduledTask -TaskName $PrimaryTask -ErrorAction SilentlyContinue
if (-not $task) { throw "Primary Radar task not registered." }

$age = Get-HeartbeatAgeSeconds
if ($task.State -ne "Running") {
    Start-ScheduledTask -TaskName $PrimaryTask
    exit 0
}

if ($age -gt $MaxHeartbeatAgeSeconds) {
    Stop-ScheduledTask -TaskName $PrimaryTask -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName $PrimaryTask
}
