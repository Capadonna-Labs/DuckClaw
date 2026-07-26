#!/usr/bin/env pwsh
# Build duckclaw-admin standalone and sync to the installed DuckClaw desktop bundle.
# DEV HOTFIX ONLY - not a substitute for the Tauri auto-updater (NSIS + latest.json).
# Use when NSIS reinstall is not done but admin UI fixes must land on disk.
# Does NOT copy duckclaw_backend.exe; production sidecar comes from the installer bundle.

param(
    [switch]$SkipBuild,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "DuckClaw")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$AdminSrc = Join-Path $RepoRoot "apps\duckclaw-admin"
$AdminDest = Join-Path $InstallRoot "resources\admin-ui"
$DesktopEnv = Join-Path $InstallRoot "desktop.env"

if (-not $SkipBuild) {
    Write-Host "==> Building duckclaw-admin..."
    Push-Location $AdminSrc
    $tempNpmrc = $false
    try {
        if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
            throw "pnpm not found"
        }
        if (-not (Test-Path ".npmrc")) {
            @"
node-linker=hoisted
symlink=false
"@ | Set-Content ".npmrc" -Encoding ascii
            $tempNpmrc = $true
        }
        pnpm install --include=dev 2>$null
        if ($LASTEXITCODE -ne 0) { pnpm install --include=dev }
        $prevNodeEnv = $env:NODE_ENV
        Remove-Item Env:NODE_ENV -ErrorAction SilentlyContinue
        $env:DUCKCLAW_ADMIN_RELAX_BUILD = "1"
        pnpm run build
        if ($LASTEXITCODE -ne 0) { throw "pnpm build failed (exit $LASTEXITCODE)" }
        if ($null -ne $prevNodeEnv) { $env:NODE_ENV = $prevNodeEnv }
    } finally {
        if ($tempNpmrc) { Remove-Item ".npmrc" -Force -ErrorAction SilentlyContinue }
        Pop-Location
    }
}

$standalone = Join-Path $AdminSrc ".next\standalone"
if (-not (Test-Path $standalone)) {
    throw "Missing $standalone; run build first"
}

Write-Host "==> Syncing admin-ui -> $AdminDest"
New-Item -ItemType Directory -Force -Path $AdminDest | Out-Null

function Copy-TreeOverlay {
    param([string]$Src, [string]$Dest)
    if (-not (Test-Path $Src)) { return }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Copy-Item -Path (Join-Path $Src "*") -Destination $Dest -Recurse -Force
}

Copy-TreeOverlay -Src $standalone -Dest $AdminDest

$staticSrc = Join-Path $AdminSrc ".next\static"
if (Test-Path $staticSrc) {
    $staticDest = Join-Path $AdminDest ".next\static"
    New-Item -ItemType Directory -Force -Path (Split-Path $staticDest) | Out-Null
    Copy-TreeOverlay -Src $staticSrc -Dest $staticDest
}

$publicSrc = Join-Path $AdminSrc "public"
if (Test-Path $publicSrc) {
    Copy-TreeOverlay -Src $publicSrc -Dest (Join-Path $AdminDest "public")
}

$entry = "server.js"
$nested = Join-Path $AdminDest "apps\duckclaw-admin\server.js"
if (Test-Path $nested) { $entry = "apps\duckclaw-admin\server.js" }
Set-Content -Path (Join-Path $AdminDest "SERVER_ENTRY") -Value $entry -NoNewline

$envLocal = Join-Path $AdminDest ".env.local"
$lines = @(
    "# DuckClaw desktop runtime (sync script)",
    "LITE_MODE=1",
    "DUCKCLAW_SPAWN_PROFILE=1",
    "DUCKCLAW_DISABLE_DOTENV=1",
    "NEXT_PUBLIC_DUCKCLAW_DESKTOP=1",
    "DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000"
)
if (Test-Path $DesktopEnv) {
    Get-Content $DesktopEnv | ForEach-Object {
        $t = $_.Trim()
        if ($t -and -not $t.StartsWith("#") -and $t -match '^DUCKCLAW_|^OPENROUTER_') {
            $k = $t.Split("=", 2)[0].Trim()
            if ($k -notin @("LITE_MODE", "DUCKCLAW_SPAWN_PROFILE", "DUCKCLAW_DISABLE_DOTENV", "DUCKCLAW_GATEWAY_URL")) {
                $lines += $t
            }
        }
    }
}
Set-Content -Path $envLocal -Value ($lines -join "`n") -Encoding utf8

Write-Host "==> Freeing port 3000 (admin node)..."
$conn = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host "Done. Restart DuckClaw desktop to load the new admin UI."
Write-Host "Admin path: $AdminDest"
