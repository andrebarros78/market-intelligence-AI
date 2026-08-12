#requires -version 5.1
[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path $env:USERPROFILE 'Documents\Market-Intelligence-Git-Recovery'),
    [string[]]$CandidateRoots = @(
        'C:\D-MIRROR\Projetos\API-ML',
        'C:\D-MIRROR\Projetos\API-ML-RECUPERACAO-BASE-20260729-1715',
        'C:\D-MIRROR\Projetos\API-ML-RECUPERACAO-ESTADO-20260729-1712',
        'D:\Projetos\API-ML',
        'C:\Projetos\API-ML'
    )
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    throw 'Git nao encontrado no PATH.'
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $OutputRoot $timestamp
$evidenceRoot = Join-Path $out 'git-evidence'
$safeRoot = Join-Path $out 'recovered-safe'
New-Item -ItemType Directory -Force -Path $out,$evidenceRoot,$safeRoot | Out-Null

$knownCommits = @(
    '9927420f292fdd32b15c0631c5c3d09933f9c0b4',
    'bf56b52633550ec1968dfe7b06dadfe5969ac4a2'
)

$textExtensions = @(
    '.py','.ps1','.psm1','.psd1','.sql','.toml','.yaml','.yml','.json','.ini','.cfg','.conf',
    '.md','.txt','.rst','.csv','.xml','.html','.css','.scss','.js','.jsx','.ts','.tsx','.sh','.bat','.cmd'
)

function Invoke-GitCapture {
    param(
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][string[]]$GitArguments
    )

    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath 'git.exe' `
            -ArgumentList $GitArguments `
            -WorkingDirectory $Repo `
            -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $stdoutRaw = ''
        $stderrRaw = ''
        if (Test-Path -LiteralPath $stdoutPath) { $stdoutRaw = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $stderrPath) { $stderrRaw = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue }

        $stdoutLines = if ([string]::IsNullOrEmpty($stdoutRaw)) { @() } else { @($stdoutRaw -split "`r?`n" | Where-Object { $_ -ne '' }) }
        $stderrLines = if ([string]::IsNullOrEmpty($stderrRaw)) { @() } else { @($stderrRaw -split "`r?`n" | Where-Object { $_ -ne '' }) }

        return [pscustomobject]@{
            ExitCode = $p.ExitCode
            StdOutRaw = $stdoutRaw
            StdErrRaw = $stderrRaw
            StdOutLines = $stdoutLines
            StdErrLines = $stderrLines
            Lines = @($stdoutLines) + @($stderrLines)
        }
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 999
            StdOutRaw = ''
            StdErrRaw = $_.Exception.Message
            StdOutLines = @()
            StdErrLines = @($_.Exception.Message)
            Lines = @($_.Exception.Message)
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath,$stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Save-GitCommand {
    param(
        [string]$Repo,
        [string[]]$GitArguments,
        [string]$Destination
    )
    $r = Invoke-GitCapture -Repo $Repo -GitArguments $GitArguments
    $header = @(
        ('EXIT_CODE=' + $r.ExitCode),
        ('COMMAND=git ' + ($GitArguments -join ' ')),
        '--- STDOUT ---'
    )
    $body = @($r.StdOutLines) + @('--- STDERR ---') + @($r.StdErrLines)
    $header + $body | Set-Content -LiteralPath $Destination -Encoding UTF8
    return $r
}

function Get-SafeRepoId {
    param([string]$Path,[int]$Index)
    $leaf = Split-Path -Path $Path -Leaf
    if (-not $leaf) { $leaf = 'repo' }
    $leaf = $leaf -replace '[^A-Za-z0-9._-]','_'
    return ('{0:D2}-{1}' -f $Index,$leaf)
}

function Sanitize-RemoteLine {
    param([string]$Line)
    $value = $Line
    $value = $value -replace '(https?://)[^/@\s]+:[^/@\s]+@','$1***:***@'
    $value = $value -replace '(https?://)[^/@\s]+@','$1***@'
    return $value
}

function Test-StrongSecretContent {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $false }

    $strongPatterns = @(
        '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        '(?i)\bAPP_USR-[A-Za-z0-9._-]{12,}',
        '(?i)\bTG-[A-Za-z0-9._-]{12,}',
        '(?i)\bgh[pousr]_[A-Za-z0-9]{20,}',
        '(?i)\bAKIA[0-9A-Z]{16}\b',
        '(?i)Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~+\-/=]{16,}',
        '(?i)(postgres(?:ql)?|mysql|mariadb)://[^\s:/]+:[^\s@/]+@'
    )
    foreach ($pattern in $strongPatterns) {
        if ($Text -match $pattern) { return $true }
    }

    $assignmentPattern = '(?im)^\s*(client_secret|access_token|refresh_token|api[_-]?key|password)\s*[:=]\s*["'']([^"'']{16,})["'']\s*$'
    foreach ($m in [regex]::Matches($Text,$assignmentPattern)) {
        $value = $m.Groups[2].Value
        if ($value -notmatch '(?i)(fake|dummy|synthetic|test|example|placeholder|changeme|not[-_ ]?real|xxxx|<|\$\{|env\.)') {
            return $true
        }
    }
    return $false
}

function Test-ShareableTextPath {
    param([string]$Path)
    $name = [IO.Path]::GetFileName($Path)
    $ext = [IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($textExtensions -contains $ext) { return $true }
    return ($name -in @('Dockerfile','Makefile','Procfile','.gitignore','.gitattributes'))
}

function Get-Sha256Text {
    param([string]$Text)
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Write-SafeRecoveredText {
    param(
        [string]$RepoId,
        [string]$LogicalPath,
        [string]$Text,
        [string]$ObjectSha,
        [string]$Origin,
        [System.Collections.Generic.List[object]]$Manifest
    )

    $secret = Test-StrongSecretContent -Text $Text
    $Manifest.Add([pscustomobject]@{
        repo_id = $RepoId
        logical_path = $LogicalPath
        git_object = $ObjectSha
        origin = $Origin
        strong_secret_detected = $secret
        sha256 = (Get-Sha256Text -Text $Text)
        exported = ((-not $secret) -and (Test-ShareableTextPath -Path $LogicalPath))
    })

    if ($secret) { return }
    if (-not (Test-ShareableTextPath -Path $LogicalPath)) { return }

    $safeRelative = $LogicalPath -replace '^[A-Za-z]:','' -replace '^[\\/]+',''
    $dest = Join-Path (Join-Path $safeRoot $RepoId) $safeRelative
    $parent = Split-Path -Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $Text | Set-Content -LiteralPath $dest -Encoding UTF8
}

function Find-HistoricalGitIndexes {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    return @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force -Filter 'git-index.txt' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '(?i)recovery|recuperacao|report|relatorio' })
}

Write-Host '=== MARKET INTELLIGENCE IA - COLETA GIT DE RECUPERACAO V2 ==='
Write-Host "Saida: $out"
Write-Host 'Modo somente leitura: nenhum reset, checkout, clean, restore, commit ou push.'

$roots = @($CandidateRoots | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { (Resolve-Path -LiteralPath $_).Path } | Sort-Object -Unique)
$repoSummary = New-Object 'System.Collections.Generic.List[object]'
$objectManifest = New-Object 'System.Collections.Generic.List[object]'
$historicalIndexManifest = New-Object 'System.Collections.Generic.List[object]'

$repoIndex = 0
foreach ($repo in $roots) {
    $repoIndex++
    $repoId = Get-SafeRepoId -Path $repo -Index $repoIndex
    $dest = Join-Path $evidenceRoot $repoId
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    $gitMarker = Join-Path $repo '.git'
    $hasGit = Test-Path -LiteralPath $gitMarker
    Write-Host "[$repoIndex/$($roots.Count)] $repo  GIT=$hasGit"

    if (-not $hasGit) {
        $repoSummary.Add([pscustomobject]@{
            repo_id=$repoId; repo=$repo; has_git=$false; head_valid=$false; head=''; branch='';
            status_exit=''; fsck_exit=''; historical_indexes=0; historical_objects_found=0; historical_objects_missing=0
        })
        continue
    }

    $head = Save-GitCommand -Repo $repo -GitArguments @('rev-parse','--verify','HEAD') -Destination (Join-Path $dest 'head.txt')
    $branch = Save-GitCommand -Repo $repo -GitArguments @('branch','--show-current') -Destination (Join-Path $dest 'branch.txt')
    $status = Save-GitCommand -Repo $repo -GitArguments @('status','--porcelain=v1','-uall','--branch') -Destination (Join-Path $dest 'status.txt')
    Save-GitCommand -Repo $repo -GitArguments @('show-ref','--head') -Destination (Join-Path $dest 'show-ref.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('branch','-a','-vv','--no-abbrev') -Destination (Join-Path $dest 'branches.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('tag','-n') -Destination (Join-Path $dest 'tags.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('worktree','list','--porcelain') -Destination (Join-Path $dest 'worktrees.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('stash','list','--date=iso') -Destination (Join-Path $dest 'stashes.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('reflog','--all','--date=iso-strict','--pretty=format:%H|%gD|%cI|%gs') -Destination (Join-Path $dest 'reflog-all.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('log','--all','-300','--date=iso-strict','--pretty=format:%H|%P|%cI|%an|%s') -Destination (Join-Path $dest 'log-all.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('ls-files','--stage') -Destination (Join-Path $dest 'index-stage.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('ls-files','--deleted') -Destination (Join-Path $dest 'deleted.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('ls-files','--others','--exclude-standard') -Destination (Join-Path $dest 'untracked.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('diff','--name-status') -Destination (Join-Path $dest 'diff-names.txt') | Out-Null
    Save-GitCommand -Repo $repo -GitArguments @('diff','--cached','--name-status') -Destination (Join-Path $dest 'diff-cached-names.txt') | Out-Null
    $fsck = Save-GitCommand -Repo $repo -GitArguments @('fsck','--full','--unreachable','--no-reflogs','--no-progress') -Destination (Join-Path $dest 'fsck-unreachable.txt')
    Save-GitCommand -Repo $repo -GitArguments @('rev-list','--all','--objects') -Destination (Join-Path $dest 'object-list.txt') | Out-Null

    $remote = Invoke-GitCapture -Repo $repo -GitArguments @('remote','-v')
    @('EXIT_CODE=' + $remote.ExitCode) + @($remote.StdOutLines | ForEach-Object { Sanitize-RemoteLine ([string]$_) }) + @($remote.StdErrLines) |
        Set-Content -LiteralPath (Join-Path $dest 'remotes-sanitized.txt') -Encoding UTF8

    $knownCommitRows = New-Object 'System.Collections.Generic.List[object]'
    foreach ($commit in $knownCommits) {
        $probe = Invoke-GitCapture -Repo $repo -GitArguments @('cat-file','-e',($commit + '^{commit}'))
        $exists = ($probe.ExitCode -eq 0)
        $knownCommitRows.Add([pscustomobject]@{ commit=$commit; exists=$exists; exit_code=$probe.ExitCode })
        if ($exists) {
            Save-GitCommand -Repo $repo -GitArguments @('show','--no-patch','--decorate','--date=iso-strict','--pretty=fuller',$commit) -Destination (Join-Path $dest ("commit-$commit.txt")) | Out-Null
            Save-GitCommand -Repo $repo -GitArguments @('ls-tree','-r','--full-tree',$commit) -Destination (Join-Path $dest ("tree-$commit.txt")) | Out-Null
        }
    }
    $knownCommitRows | Export-Csv -LiteralPath (Join-Path $dest 'known-commits.csv') -NoTypeInformation -Encoding UTF8

    $historicalIndexes = @(Find-HistoricalGitIndexes -Root $repo)
    $foundCount = 0
    $missingCount = 0

    foreach ($indexFile in $historicalIndexes) {
        $indexId = ($indexFile.Directory.Name + '-' + $indexFile.BaseName) -replace '[^A-Za-z0-9._-]','_'
        $indexRows = New-Object 'System.Collections.Generic.List[object]'

        foreach ($line in @(Get-Content -LiteralPath $indexFile.FullName -ErrorAction SilentlyContinue)) {
            if ($line -notmatch '^\s*([0-7]{6})\s+([0-9a-fA-F]{40,64})\s+([0-3])\s+(.+)$') { continue }
            $mode = $Matches[1]
            $sha = $Matches[2].ToLowerInvariant()
            $stage = $Matches[3]
            $path = $Matches[4]

            $probe = Invoke-GitCapture -Repo $repo -GitArguments @('cat-file','-e',($sha + '^{blob}'))
            $exists = ($probe.ExitCode -eq 0)
            if ($exists) { $foundCount++ } else { $missingCount++ }

            $historicalIndexManifest.Add([pscustomobject]@{
                repo_id=$repoId; index_file=$indexFile.FullName; mode=$mode; object_sha=$sha; stage=$stage; path=$path; object_exists=$exists; probe_exit=$probe.ExitCode
            })
            $indexRows.Add([pscustomobject]@{ mode=$mode; object_sha=$sha; stage=$stage; path=$path; object_exists=$exists; probe_exit=$probe.ExitCode })

            if ($exists -and (Test-ShareableTextPath -Path $path)) {
                $blob = Invoke-GitCapture -Repo $repo -GitArguments @('cat-file','-p',$sha)
                if ($blob.ExitCode -eq 0) {
                    Write-SafeRecoveredText -RepoId $repoId -LogicalPath (Join-Path ('historical-' + $indexId) $path) -Text $blob.StdOutRaw -ObjectSha $sha -Origin $indexFile.FullName -Manifest $objectManifest
                }
            }
        }
        $indexRows | Export-Csv -LiteralPath (Join-Path $dest ("historical-index-$indexId.csv")) -NoTypeInformation -Encoding UTF8
    }

    $headValue = if ($head.ExitCode -eq 0) { ($head.StdOutRaw.Trim()) } else { '' }
    $branchValue = if ($branch.ExitCode -eq 0) { ($branch.StdOutRaw.Trim()) } else { '' }
    $repoSummary.Add([pscustomobject]@{
        repo_id=$repoId
        repo=$repo
        has_git=$true
        head_valid=($head.ExitCode -eq 0)
        head=$headValue
        branch=$branchValue
        status_exit=$status.ExitCode
        fsck_exit=$fsck.ExitCode
        historical_indexes=$historicalIndexes.Count
        historical_objects_found=$foundCount
        historical_objects_missing=$missingCount
    })
}

$repoSummary | Export-Csv -LiteralPath (Join-Path $out 'repo-summary.csv') -NoTypeInformation -Encoding UTF8
$historicalIndexManifest | Export-Csv -LiteralPath (Join-Path $out 'historical-index-objects.csv') -NoTypeInformation -Encoding UTF8
$objectManifest | Export-Csv -LiteralPath (Join-Path $out 'recovered-object-manifest.csv') -NoTypeInformation -Encoding UTF8

$validRepos = @($repoSummary | Where-Object { $_.has_git })
$foundObjects = @($historicalIndexManifest | Where-Object { $_.object_exists })
$missingObjects = @($historicalIndexManifest | Where-Object { -not $_.object_exists })
$blockedObjects = @($objectManifest | Where-Object { $_.strong_secret_detected })

$summaryLines = @(
    '# Market Intelligence IA - Evidencia Git de Recuperacao V2',
    '',
    "Gerado: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
    "Raizes existentes: $($roots.Count)",
    "Repositorios Git validos: $($validRepos.Count)",
    "Repositorios com HEAD valido: $(@($validRepos | Where-Object { $_.head_valid }).Count)",
    "Objetos historicos encontrados: $($foundObjects.Count)",
    "Objetos historicos ausentes: $($missingObjects.Count)",
    "Objetos exportados/avaliados: $($objectManifest.Count)",
    "Objetos bloqueados por segredo forte: $($blockedObjects.Count)",
    '',
    'Este coletor e somente leitura. Nenhum repositorio foi alterado.',
    'HEAD invalido e outros erros Git sao registrados como evidencia e nao interrompem a coleta.'
)
$summaryLines | Set-Content -LiteralPath (Join-Path $out 'SUMMARY.md') -Encoding UTF8

$zip = "$out-SAFE-TO-SHARE.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal

Write-Host ''
Write-Host '=== COLETA GIT V2 CONCLUIDA ==='
Write-Host "RAIZES=$($roots.Count)"
Write-Host "REPOS_GIT_VALIDOS=$($validRepos.Count)"
Write-Host "HEAD_VALIDOS=$(@($validRepos | Where-Object { $_.head_valid }).Count)"
Write-Host "OBJETOS_HISTORICOS_ENCONTRADOS=$($foundObjects.Count)"
Write-Host "OBJETOS_HISTORICOS_AUSENTES=$($missingObjects.Count)"
Write-Host "OBJETOS_BLOQUEADOS_SEGREDO=$($blockedObjects.Count)"
Write-Host "RELATORIO=$out"
Write-Host "PACOTE_SEGURO=$zip"
Write-Host 'NENHUM_REPOSITORIO_FOI_MODIFICADO=TRUE'
Write-Host 'NENHUM_UPLOAD_REALIZADO=TRUE'
