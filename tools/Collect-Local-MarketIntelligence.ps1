#requires -version 5.1
[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path $env:USERPROFILE 'Documents\Market-Intelligence-Collection'),
    [string[]]$ScanRoots = @('C:\Projetos', 'C:\New Projet', 'D:\Projetos')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $out | Out-Null

$excludeDirNames = @(
    '.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'dist', 'build', '.next', '.tox', '.idea', '.vscode'
)

$projectNamePatterns = @(
    'API-ML', 'API_ML', 'API ML', 'MARKET-INTELLIGENCE', 'MARKET_INTELLIGENCE',
    'MARKET INTELLIGENCE', 'MARKET-INTELLIGENCE-AI', 'MELI', 'MERCADO-LIVRE', 'MERCADO LIVRE'
)

$secretFilePatterns = @(
    '^\.env($|\.)', 'secret', 'credential', 'token', 'apikey', 'api_key',
    '\.pem$', '\.key$', '\.p12$', '\.pfx$', 'id_rsa', 'id_ed25519'
)

$secretContentPatterns = @(
    '(?i)client[_-]?secret\s*[:=]',
    '(?i)access[_-]?token\s*[:=]',
    '(?i)refresh[_-]?token\s*[:=]',
    '(?i)api[_-]?key\s*[:=]',
    '(?i)authorization\s*:\s*bearer\s+',
    '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
)

function Test-ExcludedPath {
    param([string]$Path)
    foreach ($name in $excludeDirNames) {
        if ($Path -match [regex]::Escape([IO.Path]::DirectorySeparatorChar + $name + [IO.Path]::DirectorySeparatorChar)) {
            return $true
        }
    }
    return $false
}

function Test-ProjectPath {
    param([string]$Path)
    foreach ($pattern in $projectNamePatterns) {
        if ($Path.IndexOf($pattern, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Get-FileCategory {
    param([IO.FileInfo]$File)
    $ext = $File.Extension.ToLowerInvariant()
    $name = $File.Name.ToLowerInvariant()
    if ($name -match '^\.env($|\.)' -or $name -match 'secret|credential|token' -or $ext -in @('.pem','.key','.p12','.pfx')) { return 'secret-risk' }
    if ($ext -in @('.py','.ps1','.psm1','.ts','.tsx','.js','.jsx','.go','.rs','.sql','.sh','.bat','.cmd','.toml','.yaml','.yml','.json')) { return 'source-config' }
    if ($ext -in @('.md','.txt','.rst','.pdf','.docx','.xlsx','.csv','.html')) { return 'documentation-data' }
    if ($name -match 'test|spec|fixture') { return 'test' }
    if ($ext -in @('.db','.sqlite','.sqlite3','.bak','.dump')) { return 'database-artifact' }
    if ($ext -in @('.zip','.7z','.rar','.tar','.gz','.tgz')) { return 'archive' }
    if ($ext -in @('.log')) { return 'log' }
    return 'other'
}

function Get-Sha256Safe {
    param([IO.FileInfo]$File)
    try {
        return (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    } catch {
        return $null
    }
}

function Get-GitSnapshot {
    param([string]$ProjectPath)
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { return $null }
    if (-not (Test-Path (Join-Path $ProjectPath '.git'))) { return $null }

    $result = [ordered]@{ path = $ProjectPath }
    Push-Location $ProjectPath
    try {
        $result.branch = (& git branch --show-current 2>$null | Out-String).Trim()
        $result.head = (& git rev-parse HEAD 2>$null | Out-String).Trim()
        $result.status = @(& git status --porcelain=v1 2>$null)
        $result.remotes = @(& git remote -v 2>$null)
        $result.tags = @(& git tag --points-at HEAD 2>$null)
        $result.last_commits = @(& git log -10 --pretty=format:'%H|%cI|%s' 2>$null)
        $result.fsck = @(& git fsck --no-progress 2>&1)
    } catch {
        $result.error = $_.Exception.Message
    } finally {
        Pop-Location
    }
    return [pscustomobject]$result
}

Write-Host '=== MARKET INTELLIGENCE IA - COLETA LOCAL SOMENTE LEITURA ==='
Write-Host "Saida: $out"

$candidateDirs = New-Object System.Collections.Generic.List[string]
foreach ($root in $ScanRoots) {
    if (-not (Test-Path $root)) { continue }

    if (Test-ProjectPath $root) { $candidateDirs.Add((Resolve-Path $root).Path) }

    Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-ExcludedPath $_.FullName) -and (Test-ProjectPath $_.FullName) } |
        ForEach-Object { $candidateDirs.Add($_.FullName) }
}

# Sempre inclui caminhos historicamente usados, se existirem.
$known = @(
    'D:\Projetos\API-ML',
    'C:\Projetos\API-ML',
    'C:\New Projet\API-ML',
    'D:\Projetos\market-intelligence-AI',
    'C:\Projetos\market-intelligence-AI',
    'C:\New Projet\market-intelligence-AI'
)
foreach ($p in $known) {
    if (Test-Path $p) { $candidateDirs.Add((Resolve-Path $p).Path) }
}

# Reduz subpastas duplicadas quando um diretório pai já representa o projeto.
$projects = @($candidateDirs | Sort-Object -Unique | Sort-Object Length)
$selectedProjects = New-Object System.Collections.Generic.List[string]
foreach ($p in $projects) {
    $covered = $false
    foreach ($selected in $selectedProjects) {
        if ($p.StartsWith($selected + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            $covered = $true
            break
        }
    }
    if (-not $covered) { $selectedProjects.Add($p) }
}

$fileInventory = New-Object System.Collections.Generic.List[object]
$secretRisks = New-Object System.Collections.Generic.List[object]
$gitSnapshots = New-Object System.Collections.Generic.List[object]

foreach ($project in $selectedProjects) {
    Write-Host "Coletando: $project"
    $gitState = Get-GitSnapshot -ProjectPath $project
    if ($gitState) { $gitSnapshots.Add($gitState) }

    Get-ChildItem -LiteralPath $project -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-ExcludedPath $_.FullName) } |
        ForEach-Object {
            $file = $_
            $relative = $file.FullName.Substring($project.Length).TrimStart('\')
            $category = Get-FileCategory -File $file
            $hash = Get-Sha256Safe -File $file

            $record = [pscustomobject][ordered]@{
                project_root = $project
                relative_path = $relative
                full_path = $file.FullName
                category = $category
                extension = $file.Extension
                size_bytes = $file.Length
                modified_utc = $file.LastWriteTimeUtc.ToString('o')
                sha256 = $hash
            }
            $fileInventory.Add($record)

            $nameRisk = $false
            foreach ($pattern in $secretFilePatterns) {
                if ($file.Name -match $pattern) { $nameRisk = $true; break }
            }
            if ($nameRisk) {
                $secretRisks.Add([pscustomobject]@{
                    project_root = $project
                    relative_path = $relative
                    risk = 'filename'
                    rule = 'secret-like filename'
                })
            }

            # Conteúdo: somente arquivos texto pequenos. Nunca grava o valor encontrado.
            if ($file.Length -le 2MB -and $file.Extension.ToLowerInvariant() -in @('.py','.ps1','.psm1','.ts','.tsx','.js','.jsx','.go','.rs','.sql','.sh','.bat','.cmd','.toml','.yaml','.yml','.json','.ini','.cfg','.conf','.txt','.md','.env')) {
                try {
                    $text = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction Stop
                    foreach ($pattern in $secretContentPatterns) {
                        if ($text -match $pattern) {
                            $secretRisks.Add([pscustomobject]@{
                                project_root = $project
                                relative_path = $relative
                                risk = 'content-pattern'
                                rule = $pattern
                            })
                        }
                    }
                } catch {}
            }
        }
}

$selectedProjects | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'projects.json') -Encoding UTF8
$fileInventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'inventory.json') -Encoding UTF8
$fileInventory | Export-Csv -LiteralPath (Join-Path $out 'inventory.csv') -NoTypeInformation -Encoding UTF8
$gitSnapshots | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'git-state.json') -Encoding UTF8
$secretRisks | Sort-Object project_root, relative_path, risk -Unique | Export-Csv -LiteralPath (Join-Path $out 'secret-risks.csv') -NoTypeInformation -Encoding UTF8

$summary = @()
$summary += '# Market Intelligence IA - coleta local'
$summary += ''
$summary += "Gerado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
$summary += "Projetos encontrados: $($selectedProjects.Count)"
$summary += "Arquivos inventariados: $($fileInventory.Count)"
$summary += "Sinais de segredo: $($secretRisks.Count)"
$summary += ''
$summary += '## Projetos'
foreach ($p in $selectedProjects) { $summary += "- $p" }
$summary += ''
$summary += '## Regras de segurança'
$summary += '- Nenhum arquivo do projeto foi enviado para a internet.'
$summary += '- Nenhum valor de segredo foi copiado para os relatórios.'
$summary += '- Bancos, logs e arquivos potencialmente sensíveis foram apenas inventariados e hasheados.'
$summary += '- O próximo passo deve selecionar e sanitizar os arquivos antes de qualquer push.'
$summary | Set-Content -LiteralPath (Join-Path $out 'SUMMARY.md') -Encoding UTF8

$zip = "$out.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal

Write-Host ''
Write-Host '=== COLETA CONCLUIDA ==='
Write-Host "PROJETOS=$($selectedProjects.Count)"
Write-Host "ARQUIVOS=$($fileInventory.Count)"
Write-Host "SINAIS_SEGREDO=$($secretRisks.Count)"
Write-Host "RELATORIO=$out"
Write-Host "PACOTE=$zip"
Write-Host 'NENHUM_ARQUIVO_FOI_ENVIADO_AO_GITHUB=TRUE'
