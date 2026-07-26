#!/usr/bin/env pwsh
# Build signed DuckClaw desktop installer + latest.json for GitHub Releases.
#
# Prereq: scripts/setup_desktop_signing.ps1 (once), gh auth, TAURI_SIGNING_PRIVATE_KEY optional in CI.
#
# Usage:
#   .\scripts\release_desktop.ps1 -Version 0.2.0 -Notes "Bug fixes"
#   .\scripts\release_desktop.ps1 -Version 0.2.0 -DryRun

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$Notes = "",
    [switch]$DryRun,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot "packages\desktop"
$TauriRoot = Join-Path $DesktopRoot "src-tauri"
$TauriConf = Join-Path $TauriRoot "tauri.conf.json"
$BundleDir = Join-Path $TauriRoot "target\release\bundle\nsis"

function Get-GitHubRepoSlug {
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        $slug = gh repo view --json nameWithOwner -q .nameWithOwner 2>$null
        if ($slug) { return $slug.Trim() }
    }
    $remote = git -C $RepoRoot remote get-url origin 2>$null
    if ($remote -match 'github\.com[:/]([^/]+/[^/.]+)') {
        return $Matches[1] -replace '\.git$', ''
    }
    throw "Cannot resolve GitHub owner/repo from origin remote"
}

function Set-DesktopVersion {
    param([string]$Ver)
    $cargoToml = Join-Path $TauriRoot "Cargo.toml"
    (Get-Content $cargoToml -Raw) -replace '(?m)^version = ".*"$', "version = `"$Ver`"" | Set-Content $cargoToml -NoNewline
    $pkgJson = Join-Path $DesktopRoot "package.json"
    $pkg = Get-Content $pkgJson -Raw | ConvertFrom-Json
    $pkg.version = $Ver
    $out = $pkg | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($pkgJson, $out, [System.Text.UTF8Encoding]::new($false))
    $conf = Get-Content $TauriConf -Raw -Encoding UTF8 | ConvertFrom-Json
    $conf.version = $Ver
    $confOut = $conf | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($TauriConf, $confOut, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Version set to $Ver"
}

$pubPath = Join-Path $DesktopRoot ".tauri\duckclaw.key.pub"
if (-not (Test-Path $pubPath)) {
    Write-Host "==> Generating Minisign keys..."
    & (Join-Path $RepoRoot "scripts\setup_desktop_signing.ps1")
}

Set-DesktopVersion -Ver $Version

if (-not $SkipBuild) {
    & (Join-Path $RepoRoot "scripts\build_desktop.ps1")
}

$setup = Get-ChildItem $BundleDir -Filter "DuckClaw_*_x64-setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw "No NSIS setup exe under $BundleDir" }

$sigPath = "$($setup.FullName).sig"
if (-not (Test-Path $sigPath)) { throw "Missing signature file: $sigPath (createUpdaterArtifacts enabled?)" }

$signature = (Get-Content $sigPath -Raw).Trim()
$tag = "v$Version"
$assetName = $setup.Name
$repoSlug = Get-GitHubRepoSlug
$downloadUrl = "https://github.com/$repoSlug/releases/download/$tag/$assetName"

$latest = @{
    version   = $Version
    notes     = if ($Notes) { $Notes } else { "DuckClaw desktop $Version" }
    pub_date  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    platforms = @{
        "windows-x86_64" = @{
            signature = $signature
            url       = $downloadUrl
        }
    }
} | ConvertTo-Json -Depth 5

$latestPath = Join-Path $BundleDir "latest.json"
[System.IO.File]::WriteAllText($latestPath, $latest, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $latestPath"

Write-Host ""
Write-Host "Release assets:"
Write-Host "  $($setup.FullName)"
Write-Host "  $latestPath"

if ($DryRun) {
    Write-Host ""
    Write-Host "DryRun - skipping gh release."
    Get-Content $latestPath
    exit 0
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "gh CLI not found. Install GitHub CLI or use -DryRun and upload manually."
}

gh release view $tag 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh release create $tag $setup.FullName $latestPath --title "DuckClaw $tag" --notes $Notes
} else {
    gh release upload $tag $setup.FullName $latestPath --clobber
}
Write-Host "Published $tag"
