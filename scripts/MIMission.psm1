$script:MIBaseUri = "http://127.0.0.1:8785"
$script:MITokenPath = "C:\New Projet\market-intelligence-AI\runtime\config\mission-api-token.txt"

function Get-MIHeaders {
    if (-not (Test-Path $script:MITokenPath)) { throw "Mission API token not provisioned." }
    $token = (Get-Content -Raw -Path $script:MITokenPath).Trim()
    return @{ Authorization = "Bearer $token" }
}

function Invoke-MIPostJson {
    param([Parameter(Mandatory=$true)][string]$Uri,[Parameter(Mandatory=$true)][string]$Json)
    if (-not (Test-Path $script:MITokenPath)) { throw "Mission API token not provisioned." }
    $token = (Get-Content -Raw -Path $script:MITokenPath).Trim()
    $client = [System.Net.Http.HttpClient]::new()
    try {
        $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $token)
        $content = [System.Net.Http.StringContent]::new($Json, [System.Text.Encoding]::UTF8, 'application/json')
        try {
            $response = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
            $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not $response.IsSuccessStatusCode) { throw "Mission API HTTP $([int]$response.StatusCode): $text" }
            if ($text) { return $text | ConvertFrom-Json }
        }
        finally { $content.Dispose() }
    }
    finally { $client.Dispose() }
}

function Invoke-MIMission {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Objective,
        [ValidateSet('USER','GPT')][string]$Origin='USER',
        [ValidateRange(0,100)][int]$Priority=50
    )
    $body = @{
        objective=$Objective; origin=$Origin; mission_type='DIRECTED';
        marketplace_scope=@('mercadolivre'); authority='owner_read_only'; priority=$Priority
    } | ConvertTo-Json -Depth 6
    Invoke-MIPostJson -Uri "$script:MIBaseUri/v1/missions" -Json $body
}

function Invoke-MIFollowUp {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$MissionId,
        [Parameter(Mandatory=$true)][string]$Question,
        [ValidateSet('deepen','challenge','continue')][string]$Mode='deepen',
        [string]$SourceFindingId,
        [ValidateRange(0,100)][int]$Priority=70
    )
    $payload = @{question=$Question; mode=$Mode; priority=$Priority}
    if($SourceFindingId){$payload.source_finding_id=$SourceFindingId}
    $body = $payload | ConvertTo-Json -Depth 6
    Invoke-MIPostJson -Uri "$script:MIBaseUri/v1/missions/$MissionId/follow-ups" -Json $body
}

function Get-MIMission {
    [CmdletBinding(DefaultParameterSetName='Latest')]
    param(
        [Parameter(ParameterSetName='Id',Mandatory=$true)][string]$Id,
        [Parameter(ParameterSetName='Latest')][switch]$Latest
    )
    $headers=Get-MIHeaders
    if($PSCmdlet.ParameterSetName -eq 'Id'){ return Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$Id/status" -Headers $headers }
    $all=Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions?limit=1" -Headers $headers
    if($all.Count -gt 0){ return $all[0] }
}

function Get-MIReport {
    [CmdletBinding(DefaultParameterSetName='Latest')]
    param(
        [Parameter(ParameterSetName='Id',Mandatory=$true)][string]$Id,
        [Parameter(ParameterSetName='Latest')][switch]$Latest
    )
    $headers=Get-MIHeaders
    if($PSCmdlet.ParameterSetName -eq 'Id'){ return Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$Id/report" -Headers $headers }
    Invoke-RestMethod -Uri "$script:MIBaseUri/v1/reports/latest" -Headers $headers
}

function Get-MIHealth { Invoke-RestMethod -Uri "$script:MIBaseUri/v1/mission-system/health" -Headers (Get-MIHeaders) }
function Get-MIBrief { param([switch]$Unread); $suffix=if($Unread){'/unread'}else{''}; Invoke-RestMethod -Uri "$script:MIBaseUri/v1/intelligence/brief$suffix" -Headers (Get-MIHeaders) }
function Get-MIContext { Invoke-RestMethod -Uri "$script:MIBaseUri/v1/intelligence/context" -Headers (Get-MIHeaders) }

function Get-MIInbox {
    [CmdletBinding()]
    param([ValidateSet('UNREAD','READ','ACKNOWLEDGED')][string]$Status,[ValidateRange(1,200)][int]$Limit=50)
    $uri="$script:MIBaseUri/v1/intelligence/inbox?limit=$Limit"
    if($Status){$uri += "&status=$Status"}
    $result = Invoke-RestMethod -Uri $uri -Headers (Get-MIHeaders)
    $result | ForEach-Object { Write-Output $_ }
}

function Get-MIEvidence {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$MissionId)
    $result = Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$MissionId/evidence" -Headers (Get-MIHeaders)
    $result | ForEach-Object { Write-Output $_ }
}

function Get-MIThread {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$ThreadId)
    Invoke-RestMethod -Uri "$script:MIBaseUri/v1/threads/$ThreadId" -Headers (Get-MIHeaders)
}

function Get-MITimeline {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$MissionId)
    Invoke-RestMethod -Uri "$script:MIBaseUri/v1/missions/$MissionId/timeline" -Headers (Get-MIHeaders)
}

function Read-MIInboxItem {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Id)
    Invoke-RestMethod -Method Post -Uri "$script:MIBaseUri/v1/intelligence/inbox/$Id/read" -Headers (Get-MIHeaders)
}

Export-ModuleMember -Function Invoke-MIMission,Invoke-MIFollowUp,Get-MIMission,Get-MIReport,Get-MIHealth,Get-MIBrief,Get-MIInbox,Get-MIContext,Get-MIEvidence,Get-MIThread,Get-MITimeline,Read-MIInboxItem
