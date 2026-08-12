#requires -version 5.1
[CmdletBinding()]
param(
    [string]$Repo = 'C:\D-MIRROR\Projetos\API-ML',
    [string]$OutputRoot = (Join-Path $env:USERPROFILE 'Documents\Market-Intelligence-Dangling-Recovery')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$targets = @(
    '37b1287a4851f749cf165a57b6cfc3dcdf88d2c6',
    '9d43dbcb603cc7c70311253643476cfa7797b38a',
    'a01a0e40dc76690a98268de6aa70ee5d56abf78e'
)

if (-not (Test-Path -LiteralPath $Repo)) { throw "Repositorio nao encontrado: $Repo" }
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'Git nao encontrado.' }

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Invoke-GitText {
    param([string[]]$GitArguments)
    $stdout = [IO.Path]::GetTempFileName()
    $stderr = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath 'git.exe' -ArgumentList $GitArguments -WorkingDirectory $Repo -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $o = if (Test-Path $stdout) { Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue } else { '' }
        $e = if (Test-Path $stderr) { Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue } else { '' }
        return [pscustomobject]@{ ExitCode=$p.ExitCode; StdOut=$o; StdErr=$e }
    } finally {
        Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    }
}

function Test-StrongSecret {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $false }
    $patterns = @(
        '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        '(?i)\bgh[pousr]_[A-Za-z0-9]{20,}',
        '(?i)\bAKIA[0-9A-Z]{16}\b',
        '(?i)Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~+\-/=]{16,}',
        '(?i)(postgres(?:ql)?|mysql|mariadb)://[^\s:/]+:[^\s@/]+@',
        '(?im)^\s*(client_secret|access_token|refresh_token|api[_-]?key|password)\s*[:=]\s*["'']([^"'']{16,})["'']\s*$'
    )
    foreach($p in $patterns){ if($Text -match $p){ return $true } }
    return $false
}

$manifest = New-Object 'System.Collections.Generic.List[object]'
foreach($sha in $targets){
    $type = Invoke-GitText @('cat-file','-t',$sha)
    $size = Invoke-GitText @('cat-file','-s',$sha)
    $blob = Invoke-GitText @('cat-file','-p',$sha)
    $exists = ($type.ExitCode -eq 0 -and $type.StdOut.Trim() -eq 'blob' -and $blob.ExitCode -eq 0)
    $secret = $false
    $exported = $false
    $sha256 = ''

    if($exists){
        $text = [string]$blob.StdOut
        $secret = Test-StrongSecret $text
        $bytes = [Text.Encoding]::UTF8.GetBytes($text)
        $h = [Security.Cryptography.SHA256]::Create()
        try { $sha256 = ([BitConverter]::ToString($h.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() } finally { $h.Dispose() }
        if(-not $secret){
            $text | Set-Content -LiteralPath (Join-Path $out ($sha + '.txt')) -Encoding UTF8
            $exported = $true
        }
    }

    $manifest.Add([pscustomobject]@{
        object_sha=$sha
        exists=$exists
        object_type=$(if($type.ExitCode -eq 0){$type.StdOut.Trim()}else{''})
        size_bytes=$(if($size.ExitCode -eq 0){$size.StdOut.Trim()}else{''})
        strong_secret_detected=$secret
        sha256=$sha256
        exported=$exported
    })
}

$manifest | Export-Csv -LiteralPath (Join-Path $out 'manifest.csv') -NoTypeInformation -Encoding UTF8
$zip = "$out-SAFE-TO-SHARE.zip"
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal

Write-Host '=== DANGLING BLOBS CONCLUIDO ==='
Write-Host "OBJETOS=$($manifest.Count)"
Write-Host "ENCONTRADOS=$(@($manifest | Where-Object {$_.exists}).Count)"
Write-Host "EXPORTADOS=$(@($manifest | Where-Object {$_.exported}).Count)"
Write-Host "BLOQUEADOS_SEGREDO=$(@($manifest | Where-Object {$_.strong_secret_detected}).Count)"
Write-Host "PACOTE_SEGURO=$zip"
Write-Host 'NENHUM_REPOSITORIO_FOI_MODIFICADO=TRUE'
