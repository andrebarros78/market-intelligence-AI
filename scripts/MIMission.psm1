$script:MIBaseUri = "http://127.0.0.1:8785"
$script:MITokenPath = "C:\New Projet\market-intelligence-AI\runtime\config\mission-api-token.txt"

function Get-MIHeaders {
    if (-not (Test-Path $script:MITokenPath)) { throw "Mission API token not provisioned." }
    $token=(Get-Content -Raw -Path $script:MITokenPath).Trim()
    return @{ Authorization = "Bearer $token" }
}

function Invoke-MIMission {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Objective,[ValidateSet('USER','GPT')][string]$Origin='USER',[ValidateRange(0,100)][int]$Priority=50)
    $body=@{objective=$Objective;origin=$Origin;mission_type='DIRECTED';marketplace_scope=@('mercadolivre');authority='owner_read_only';priority=$Priority}|ConvertTo-Json -Depth 5
    Invoke-RestMethod -Method Post -Uri "$script:MIBaseUri/v1/missions" -Headers (Get-MIHeaders) -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
}

function Get-MIMission {
    [CmdletBinding(DefaultParameterSetName='Latest')]
    param([Parameter(ParameterSetName='Id',Mandatory=$true)][string]$Id,[Parameter(ParameterSetName='Latest')][switch]$Latest)
    $h=Get-MIHeaders
    if($PSCmdlet.ParameterSetName -eq 'Id'){ return Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$Id/status" -Headers $h }
    $all=Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions?limit=1" -Headers $h
    if($all.Count -gt 0){ return $all[0] }
}

function Get-MIReport {
    [CmdletBinding(DefaultParameterSetName='Latest')]
    param([Parameter(ParameterSetName='Id',Mandatory=$true)][string]$Id,[Parameter(ParameterSetName='Latest')][switch]$Latest)
    $h=Get-MIHeaders
    if($PSCmdlet.ParameterSetName -eq 'Id'){ return Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$Id/report" -Headers $h }
    Invoke-RestMethod -Uri "$script:MIBaseUri/v1/reports/latest" -Headers $h
}

function Get-MIHealth { Invoke-RestMethod -Uri "$script:MIBaseUri/v1/mission-system/health" -Headers (Get-MIHeaders) }

Export-ModuleMember -Function Invoke-MIMission,Get-MIMission,Get-MIReport,Get-MIHealth
