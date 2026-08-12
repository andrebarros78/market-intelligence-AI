#requires -version 5.1
[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path $env:USERPROFILE 'Documents\Market-Intelligence-Recovery'),
    [string[]]$ScanRoots = @('C:\Projetos', 'C:\New Projet', 'C:\D-MIRROR\Projetos', 'D:\Projetos')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $OutputRoot $timestamp
$reports = Join-Path $out 'reports'
$safeRoot = Join-Path $out 'safe-files'
$gitRoot = Join-Path $out 'git-evidence'
New-Item -ItemType Directory -Force -Path $reports,$safeRoot,$gitRoot | Out-Null

$excludeDirNames = @(
    '.venv','venv','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache',
    'dist','build','.next','.tox','.idea','.vscode','coverage_html','htmlcov'
)

$projectTokens = @(
    'API-ML','API_ML','API ML','MARKET-INTELLIGENCE','MARKET_INTELLIGENCE','MARKET INTELLIGENCE',
    'MARKET-INTELLIGENCE-AI','MELI','MERCADO-LIVRE','MERCADO LIVRE'
)

$versionTokens = @('BACKUP','BKP','MIRROR','CLEAN','RECOVERY','RECOVER','OLD','ANTIGO','COPY','COPIA')

$secretNamePatterns = @(
    '^\.env($|\.)','secret','credential','token','apikey','api_key','client[_-]?secret',
    '\.pem$','\.key$','\.p12$','\.pfx$','id_rsa','id_ed25519','credentials\.json$'
)

$secretContentPatterns = @(
    '(?i)client[_-]?secret\s*[:=]\s*[^\s#]+',
    '(?i)access[_-]?token\s*[:=]\s*[^\s#]+',
    '(?i)refresh[_-]?token\s*[:=]\s*[^\s#]+',
    '(?i)api[_-]?key\s*[:=]\s*[^\s#]+',
    '(?i)authorization\s*:\s*bearer\s+[^\s]+',
    '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
)

$safeTextExtensions = @(
    '.py','.ps1','.psm1','.psd1','.ts','.tsx','.js','.jsx','.go','.rs','.sql','.sh','.bat','.cmd',
    '.toml','.yaml','.yml','.json','.ini','.cfg','.conf','.md','.txt','.rst','.csv','.xml','.html',
    '.css','.scss','.dockerfile','.gitignore','.gitattributes'
)

function Test-ExcludedDirectoryName {
    param([string]$Name)
    if ($Name -eq '.git') { return $false }
    return ($excludeDirNames -contains $Name)
}

function Test-ProjectLike {
    param([string]$Text)
    foreach ($token in $projectTokens) {
        if ($Text.IndexOf($token,[StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Test-VersionLike {
    param([string]$Text)
    foreach ($token in $versionTokens) {
        if ($Text.IndexOf($token,[StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Get-PrunedDirectories {
    param([string]$Root)
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        foreach ($dir in @(Get-ChildItem -LiteralPath $current -Directory -Force -ErrorAction SilentlyContinue)) {
            if ($dir.Name -eq '.git') { continue }
            if (Test-ExcludedDirectoryName $dir.Name) { continue }
            $dir
            $stack.Push($dir.FullName)
        }
    }
}

function Get-PrunedFiles {
    param([string]$Root)
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        foreach ($file in @(Get-ChildItem -LiteralPath $current -File -Force -ErrorAction SilentlyContinue)) { $file }
        foreach ($dir in @(Get-ChildItem -LiteralPath $current -Directory -Force -ErrorAction SilentlyContinue)) {
            if ($dir.Name -eq '.git') { continue }
            if (Test-ExcludedDirectoryName $dir.Name) { continue }
            $stack.Push($dir.FullName)
        }
    }
}

function Get-Sha256Safe {
    param([IO.FileInfo]$File)
    try { return (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant() } catch { return $null }
}

function Test-SecretFilename {
    param([IO.FileInfo]$File)
    foreach ($pattern in $secretNamePatterns) {
        if ($File.Name -match $pattern) { return $true }
    }
    return $false
}

function Test-SecretContent {
    param([IO.FileInfo]$File)
    if ($File.Length -gt 5MB) { return $false }
    try {
        $text = Get-Content -LiteralPath $File.FullName -Raw -ErrorAction Stop
        foreach ($pattern in $secretContentPatterns) {
            if ($text -match $pattern) { return $true }
        }
    } catch {}
    return $false
}

function Get-SafeRelativeProjectId {
    param([string]$Path,[int]$Index)
    $leaf = Split-Path $Path -Leaf
    $safe = ($leaf -replace '[^A-Za-z0-9._-]','_')
    return ('{0:D2}-{1}' -f $Index,$safe)
}

function Invoke-GitLines {
    param([string]$Repo,[string[]]$Args)
    Push-Location $Repo
    try {
        return @(& git @Args 2>&1)
    } catch {
        return @('ERROR: ' + $_.Exception.Message)
    } finally {
        Pop-Location
    }
}

function Sanitize-RemoteLine {
    param([string]$Line)
    $value = $Line
    $value = $value -replace '(https?://)[^/@\s]+:[^/@\s]+@','$1***:***@'
    $value = $value -replace '(https?://)[^/@\s]+@','$1***@'
    return $value
}

function Write-GitEvidence {
    param([string]$Repo,[string]$ProjectId)
    if (-not (Test-Path (Join-Path $Repo '.git'))) { return $null }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $null }

    $dest = Join-Path $gitRoot $ProjectId
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    $commands = [ordered]@{
        'head.txt'              = @('rev-parse','HEAD')
        'status.txt'            = @('status','--porcelain=v1','-uall','--branch')
        'branches.txt'          = @('branch','-a','-vv','--no-abbrev')
        'tags.txt'              = @('tag','-n')
        'worktrees.txt'         = @('worktree','list','--porcelain')
        'stashes.txt'           = @('stash','list','--date=iso')
        'reflog-all.txt'        = @('reflog','--all','--date=iso-strict','--pretty=format:%H|%gD|%cI|%gs')
        'log-all.txt'           = @('log','--all','-150','--date=iso-strict','--pretty=format:%H|%P|%cI|%an|%s')
        'deleted.txt'           = @('ls-files','--deleted')
        'untracked.txt'         = @('ls-files','--others','--exclude-standard')
        'diff-names.txt'        = @('diff','--name-status')
        'diff-cached-names.txt' = @('diff','--cached','--name-status')
        'fsck-unreachable.txt'  = @('fsck','--full','--unreachable','--no-reflogs','--no-progress')
        'object-list.txt'       = @('rev-list','--all','--objects')
    }

    foreach ($entry in $commands.GetEnumerator()) {
        $lines = Invoke-GitLines -Repo $Repo -Args $entry.Value
        $lines | Set-Content -LiteralPath (Join-Path $dest $entry.Key) -Encoding UTF8
    }

    $remoteLines = Invoke-GitLines -Repo $Repo -Args @('remote','-v') | ForEach-Object { Sanitize-RemoteLine ([string]$_) }
    $remoteLines | Set-Content -LiteralPath (Join-Path $dest 'remotes-sanitized.txt') -Encoding UTF8

    return [pscustomobject]@{
        project_id = $ProjectId
        repo = $Repo
        head = ((Invoke-GitLines -Repo $Repo -Args @('rev-parse','HEAD')) -join '').Trim()
        branch = ((Invoke-GitLines -Repo $Repo -Args @('branch','--show-current')) -join '').Trim()
        stash_count = @((Invoke-GitLines -Repo $Repo -Args @('stash','list')) | Where-Object { $_ -and ($_ -notmatch '^ERROR:') }).Count
        deleted_count = @((Invoke-GitLines -Repo $Repo -Args @('ls-files','--deleted')) | Where-Object { $_ }).Count
        untracked_count = @((Invoke-GitLines -Repo $Repo -Args @('ls-files','--others','--exclude-standard')) | Where-Object { $_ }).Count
        unreachable_count = @((Invoke-GitLines -Repo $Repo -Args @('fsck','--full','--unreachable','--no-reflogs','--no-progress')) | Where-Object { $_ -match 'unreachable|dangling' }).Count
    }
}

function Get-RecycleBinEvidence {
    $rows = New-Object 'System.Collections.Generic.List[object]'
    try {
        $shell = New-Object -ComObject Shell.Application
        $bin = $shell.Namespace(10)
        if ($bin) {
            foreach ($item in @($bin.Items())) {
                $name = [string]$item.Name
                $path = [string]$item.Path
                if ((Test-ProjectLike $name) -or (Test-ProjectLike $path) -or (Test-VersionLike $name)) {
                    $rows.Add([pscustomobject]@{
                        name = $name
                        recycle_path = $path
                        size = $item.Size
                        modified = $item.ModifyDate
                    })
                }
            }
        }
    } catch {}
    return $rows
}

Write-Host '=== MARKET INTELLIGENCE IA - RECUPERACAO FORENSE LOCAL ==='
Write-Host "Saida: $out"
Write-Host 'Modo: leitura + copia segura de arquivos texto; nenhum upload automatico.'

$candidates = New-Object 'System.Collections.Generic.List[string]'
$known = @(
    'D:\Projetos\API-ML',
    'C:\Projetos\API-ML',
    'C:\New Projet\API-ML',
    'C:\D-MIRROR\Projetos\API-ML',
    'D:\Projetos\market-intelligence-AI',
    'C:\Projetos\market-intelligence-AI',
    'C:\New Projet\market-intelligence-AI',
    'C:\D-MIRROR\Projetos\market-intelligence-AI'
)

foreach ($p in $known) {
    if (Test-Path $p) { $candidates.Add((Resolve-Path $p).Path) }
}

foreach ($root in $ScanRoots) {
    if (-not (Test-Path $root)) { continue }
    Write-Host "Descobrindo em: $root"
    if (Test-ProjectLike $root) { $candidates.Add((Resolve-Path $root).Path) }
    foreach ($dir in @(Get-PrunedDirectories -Root $root)) {
        if ((Test-ProjectLike $dir.FullName) -or ((Test-VersionLike $dir.Name) -and (Test-ProjectLike $dir.Parent.FullName))) {
            $candidates.Add($dir.FullName)
        }
    }
}

# Busca leve por arquivos soltos/archives com nomes relacionados ao projeto.
$looseRoots = @(
    (Join-Path $env:USERPROFILE 'Desktop'),
    (Join-Path $env:USERPROFILE 'Documents'),
    (Join-Path $env:USERPROFILE 'Downloads')
)
$loose = New-Object 'System.Collections.Generic.List[object]'
foreach ($root in $looseRoots) {
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notlike "$OutputRoot*" -and (Test-ProjectLike $_.Name) } |
        ForEach-Object {
            $loose.Add([pscustomobject]@{
                full_path = $_.FullName
                size_bytes = $_.Length
                modified_utc = $_.LastWriteTimeUtc.ToString('o')
                sha256 = Get-Sha256Safe $_
            })
        }
}
$loose | Export-Csv -LiteralPath (Join-Path $reports 'loose-project-files.csv') -NoTypeInformation -Encoding UTF8

$projects = @($candidates | Sort-Object -Unique | Sort-Object Length)
$selected = New-Object 'System.Collections.Generic.List[string]'
foreach ($p in $projects) {
    $covered = $false
    foreach ($parent in $selected) {
        if ($p.StartsWith($parent + '\',[StringComparison]::OrdinalIgnoreCase)) {
            # Mantem subrepo Git mesmo dentro de candidato maior.
            if (Test-Path (Join-Path $p '.git')) { continue }
            $covered = $true
            break
        }
    }
    if (-not $covered) { $selected.Add($p) }
}

$inventory = New-Object 'System.Collections.Generic.List[object]'
$sensitive = New-Object 'System.Collections.Generic.List[object]'
$safeCopied = New-Object 'System.Collections.Generic.List[object]'
$gitSummary = New-Object 'System.Collections.Generic.List[object]'
$projectMap = New-Object 'System.Collections.Generic.List[object]'

$index = 0
foreach ($project in $selected) {
    $index++
    $projectId = Get-SafeRelativeProjectId -Path $project -Index $index
    $projectMap.Add([pscustomobject]@{ project_id=$projectId; path=$project })
    Write-Host "[$index/$($selected.Count)] Analisando: $project"

    $gitState = Write-GitEvidence -Repo $project -ProjectId $projectId
    if ($gitState) { $gitSummary.Add($gitState) }

    foreach ($file in @(Get-PrunedFiles -Root $project)) {
        $relative = $file.FullName.Substring($project.Length).TrimStart('\')
        $hash = Get-Sha256Safe $file
        $nameRisk = Test-SecretFilename $file
        $contentRisk = $false

        $ext = $file.Extension.ToLowerInvariant()
        $isTextCandidate = ($safeTextExtensions -contains $ext) -or ($file.Name -in @('Dockerfile','Makefile','Procfile'))
        if ($isTextCandidate -and -not $nameRisk) { $contentRisk = Test-SecretContent $file }

        $inventory.Add([pscustomobject][ordered]@{
            project_id = $projectId
            project_root = $project
            relative_path = $relative
            full_path = $file.FullName
            extension = $file.Extension
            size_bytes = $file.Length
            modified_utc = $file.LastWriteTimeUtc.ToString('o')
            sha256 = $hash
            git_dir_excluded = $true
        })

        if ($nameRisk -or $contentRisk) {
            $sensitive.Add([pscustomobject]@{
                project_id = $projectId
                project_root = $project
                relative_path = $relative
                reason = $(if ($nameRisk -and $contentRisk) {'filename+content'} elseif ($nameRisk) {'filename'} else {'content'})
                sha256 = $hash
            })
            continue
        }

        if ($isTextCandidate -and $file.Length -le 10MB) {
            $dest = Join-Path (Join-Path $safeRoot $projectId) $relative
            $parent = Split-Path $dest -Parent
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
            try {
                Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
                $safeCopied.Add([pscustomobject]@{
                    project_id = $projectId
                    source = $file.FullName
                    relative_path = $relative
                    sha256 = $hash
                    destination = $dest
                })
            } catch {}
        }
    }
}

$projectMap | Export-Csv -LiteralPath (Join-Path $reports 'projects.csv') -NoTypeInformation -Encoding UTF8
$inventory | Export-Csv -LiteralPath (Join-Path $reports 'inventory.csv') -NoTypeInformation -Encoding UTF8
$inventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $reports 'inventory.json') -Encoding UTF8
$sensitive | Sort-Object project_id,relative_path -Unique | Export-Csv -LiteralPath (Join-Path $reports 'sensitive-skipped.csv') -NoTypeInformation -Encoding UTF8
$safeCopied | Export-Csv -LiteralPath (Join-Path $reports 'safe-copy-manifest.csv') -NoTypeInformation -Encoding UTF8
$gitSummary | Export-Csv -LiteralPath (Join-Path $reports 'git-summary.csv') -NoTypeInformation -Encoding UTF8

$hashRows = @($inventory | Where-Object { $_.sha256 })
$hashGroups = @($hashRows | Group-Object sha256)
$duplicates = foreach ($g in $hashGroups | Where-Object { $_.Count -gt 1 }) {
    [pscustomobject]@{
        sha256 = $g.Name
        copies = $g.Count
        paths = (($g.Group | ForEach-Object { $_.project_id + ':' + $_.relative_path }) -join ' | ')
    }
}
$duplicates | Export-Csv -LiteralPath (Join-Path $reports 'duplicate-hashes.csv') -NoTypeInformation -Encoding UTF8

$uniqueHashes = foreach ($g in $hashGroups | Where-Object { $_.Count -eq 1 }) {
    $row = $g.Group[0]
    [pscustomobject]@{
        sha256 = $g.Name
        project_id = $row.project_id
        relative_path = $row.relative_path
        full_path = $row.full_path
    }
}
$uniqueHashes | Export-Csv -LiteralPath (Join-Path $reports 'unique-hashes.csv') -NoTypeInformation -Encoding UTF8

$pathConflicts = foreach ($g in @($inventory | Group-Object relative_path)) {
    $distinct = @($g.Group.sha256 | Where-Object { $_ } | Sort-Object -Unique)
    if ($distinct.Count -gt 1) {
        [pscustomobject]@{
            relative_path = $g.Name
            variants = $distinct.Count
            projects = (($g.Group | ForEach-Object { $_.project_id + ':' + $_.sha256 }) -join ' | ')
        }
    }
}
$pathConflicts | Export-Csv -LiteralPath (Join-Path $reports 'path-conflicts.csv') -NoTypeInformation -Encoding UTF8

$recycle = @(Get-RecycleBinEvidence)
$recycle | Export-Csv -LiteralPath (Join-Path $reports 'recycle-bin-candidates.csv') -NoTypeInformation -Encoding UTF8

$summary = @()
$summary += '# Market Intelligence IA - Recuperacao local'
$summary += ''
$summary += "Gerado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
$summary += "Projetos/candidatos: $($selected.Count)"
$summary += "Arquivos inventariados: $($inventory.Count)"
$summary += "Arquivos texto copiados com filtro de segredo: $($safeCopied.Count)"
$summary += "Arquivos omitidos por risco de segredo: $($sensitive.Count)"
$summary += "Repositorios Git encontrados: $($gitSummary.Count)"
$summary += "Hashes duplicados: $(@($duplicates).Count)"
$summary += "Hashes unicos: $(@($uniqueHashes).Count)"
$summary += "Caminhos com conteudo divergente: $(@($pathConflicts).Count)"
$summary += "Candidatos na Lixeira: $($recycle.Count)"
$summary += ''
$summary += '## Regras'
$summary += '- Nenhum upload foi realizado.'
$summary += '- Nenhum reset, checkout, clean, restore ou alteracao foi feito nos repositorios analisados.'
$summary += '- O diretorio .git nao foi copiado para o pacote compartilhavel; apenas metadados de recuperacao foram registrados.'
$summary += '- Arquivos com nome ou conteudo semelhante a segredo foram omitidos do pacote compartilhavel.'
$summary += '- Bancos, binarios, logs e archives foram inventariados, mas nao copiados para o pacote compartilhavel.'
$summary | Set-Content -LiteralPath (Join-Path $out 'SUMMARY.md') -Encoding UTF8

$safeZip = "$out-SAFE-TO-SHARE.zip"
if (Test-Path $safeZip) { Remove-Item $safeZip -Force }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $safeZip -CompressionLevel Optimal

Write-Host ''
Write-Host '=== RECUPERACAO CONCLUIDA ==='
Write-Host "PROJETOS=$($selected.Count)"
Write-Host "ARQUIVOS=$($inventory.Count)"
Write-Host "COPIADOS_SEGUROS=$($safeCopied.Count)"
Write-Host "OMITIDOS_SENSIVEIS=$($sensitive.Count)"
Write-Host "REPOS_GIT=$($gitSummary.Count)"
Write-Host "HASHES_UNICOS=$(@($uniqueHashes).Count)"
Write-Host "CONFLITOS_DE_CAMINHO=$(@($pathConflicts).Count)"
Write-Host "LIXEIRA_CANDIDATOS=$($recycle.Count)"
Write-Host "RELATORIO=$out"
Write-Host "PACOTE_SEGURO=$safeZip"
Write-Host 'NENHUM_UPLOAD_REALIZADO=TRUE'
Write-Host 'NENHUM_REPOSITORIO_FOI_MODIFICADO=TRUE'
