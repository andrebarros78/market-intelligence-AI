[CmdletBinding()]
param(
    [string]$CacheRoot = (Join-Path $env:LOCALAPPDATA 'Market-Intelligence\Agent-Warehouse')
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$InventoryPath = Join-Path $RepoRoot 'agents\warehouse\recruits.json'
if (-not (Test-Path -LiteralPath $InventoryPath)) { throw "INVENTARIO_NAO_ENCONTRADO=$InventoryPath" }
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'GIT_NAO_ENCONTRADO' }

$inventory = Get-Content -LiteralPath $InventoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($inventory.policy.auto_execution -ne $false) { throw 'POLITICA_INVALIDA_AUTO_EXECUTION' }

New-Item -ItemType Directory -Path $CacheRoot -Force | Out-Null
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("mi-agent-warehouse-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

$repoClones = @{}
$hashRows = New-Object System.Collections.Generic.List[object]
$copied = 0
$skipped = 0

try {
    foreach ($entry in $inventory.recruits) {
        if ($entry.third_party_execution_allowed -ne $false) {
            throw "RECRUTA_COM_EXECUCAO_NAO_PERMITIDA=$($entry.id)"
        }

        $repo = [string]$entry.source_repo
        $ref = [string]$entry.source_ref
        $sourcePath = [string]$entry.source_path
        if ([string]::IsNullOrWhiteSpace($ref) -or $ref -match '^(main|master|latest)$') {
            throw "REFERENCIA_NAO_FIXADA=$($entry.id)"
        }

        if (-not $repoClones.ContainsKey($repo)) {
            $cloneDir = Join-Path $tempRoot ($repo -replace '[^A-Za-z0-9._-]', '_')
            & git.exe clone --quiet --filter=blob:none --no-checkout ("https://github.com/{0}.git" -f $repo) $cloneDir
            if ($LASTEXITCODE -ne 0) { throw "FALHA_CLONE=$repo" }

            & git.exe -C $cloneDir cat-file -e ("{0}^{{commit}}" -f $ref) 2>$null
            if ($LASTEXITCODE -ne 0) {
                & git.exe -C $cloneDir fetch --quiet --depth 1 origin $ref
                if ($LASTEXITCODE -ne 0) { throw "FALHA_FETCH_REF=$repo@$ref" }
            }
            $repoClones[$repo] = $cloneDir
        }

        $cloneDir = [string]$repoClones[$repo]
        & git.exe -C $cloneDir checkout --quiet $ref -- $sourcePath
        if ($LASTEXITCODE -ne 0) { throw "FALHA_CHECKOUT=$repo@$ref::$sourcePath" }

        $sourceLocal = Join-Path $cloneDir ($sourcePath -replace '/', '\')
        if (-not (Test-Path -LiteralPath $sourceLocal)) { throw "FONTE_NAO_MATERIALIZADA=$($entry.id)" }

        $shortRef = $ref.Substring(0, [Math]::Min(12, $ref.Length))
        $targetRoot = Join-Path $CacheRoot (Join-Path ([string]$entry.id) $shortRef)
        if (-not (Test-Path -LiteralPath $targetRoot)) {
            New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
            $targetContent = Join-Path $targetRoot 'source'
            if ((Get-Item -LiteralPath $sourceLocal).PSIsContainer) {
                Copy-Item -LiteralPath $sourceLocal -Destination $targetContent -Recurse
            } else {
                New-Item -ItemType Directory -Path $targetContent -Force | Out-Null
                Copy-Item -LiteralPath $sourceLocal -Destination (Join-Path $targetContent ([IO.Path]::GetFileName($sourceLocal)))
            }
            $copied++
        } else {
            $skipped++
        }

        Get-ChildItem -LiteralPath $targetRoot -Recurse -File | ForEach-Object {
            $h = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            $hashRows.Add([pscustomobject]@{
                recruit_id = [string]$entry.id
                source_repo = $repo
                source_ref = $ref
                source_path = $sourcePath
                local_file = $_.FullName.Substring($CacheRoot.Length).TrimStart('\')
                sha256 = $h.Hash.ToLowerInvariant()
            })
        }
    }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $manifestPath = Join-Path $CacheRoot ("MANIFEST-SHA256-{0}.json" -f $timestamp)
    $hashRows | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    Write-Host '=== ALMOXARIFADO SINCRONIZADO ==='
    Write-Host ("AGENTES_RECRUTADOS={0}" -f $inventory.recruits.Count)
    Write-Host 'ATIVADOS=0'
    Write-Host ("COPIADOS_NESTA_EXECUCAO={0}" -f $copied)
    Write-Host ("JA_EXISTENTES={0}" -f $skipped)
    Write-Host ("CACHE={0}" -f $CacheRoot)
    Write-Host ("MANIFESTO_SHA256={0}" -f $manifestPath)
    Write-Host 'NENHUM_SCRIPT_TERCEIRO_EXECUTADO=TRUE'
    Write-Host 'NENHUMA_SKILL_FOI_PROMOVIDA=TRUE'
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
