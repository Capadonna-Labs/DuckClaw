#!/usr/bin/env pwsh
# Full DuckClaw desktop build: sidecar + admin standalone + node + Tauri NSIS.
#
# Prereq: uv, pnpm, npm, Rust/cargo (tauri build), network for node download.
# Icons: src-tauri/icons/* from `pnpm exec tauri icon` using
#   apps/duckclaw-admin/public/brand/duckclaw-icon.png (or packages/desktop/app-icon.png).
#   tauri.conf.json bundle.icon already points at 32/128/256/icon.ico.
#
# Output:
#   packages/desktop/src-tauri/target/release/bundle/nsis/DuckClaw_*_x64-setup.exe

param(
    [switch]$SkipTauri,
    [switch]$SkipSidecar,
    [string]$NodeVersion = "22.17.0"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$DesktopRoot = Join-Path $RepoRoot "packages\desktop"
$TauriRoot = Join-Path $DesktopRoot "src-tauri"
$ResourcesRoot = Join-Path $TauriRoot "resources"
$AdminDest = Join-Path $ResourcesRoot "admin-ui"
$NodeDest = Join-Path $ResourcesRoot "node"
$AdminSrc = Join-Path $RepoRoot "apps\duckclaw-admin"

New-Item -ItemType Directory -Force -Path $ResourcesRoot, $AdminDest, $NodeDest | Out-Null

function Stage-AdminStandalone {
    Write-Host "==> Building duckclaw-admin (Next standalone)..."
    Push-Location $AdminSrc
    $tempNpmrc = $false
    try {
        if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
            throw "pnpm not found. Install Node.js + pnpm."
        }
        # ponytail: hoisted linker avoids Next standalone symlink EPERM on Windows without Dev Mode
        if ($IsWindows -or $env:OS -match "Windows") {
            if (-not (Test-Path ".npmrc")) {
                @"
node-linker=hoisted
symlink=false
"@ | Set-Content ".npmrc" -Encoding ascii
                $tempNpmrc = $true
                Remove-Item "node_modules" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        pnpm install --frozen-lockfile 2>$null
        if ($LASTEXITCODE -ne 0) { pnpm install }
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed (exit $LASTEXITCODE)" }
        $env:DUCKCLAW_ADMIN_RELAX_BUILD = "1"
        pnpm run build
        if ($LASTEXITCODE -ne 0) { throw "pnpm build failed (exit $LASTEXITCODE)" }
    } finally {
        if ($tempNpmrc) { Remove-Item ".npmrc" -Force -ErrorAction SilentlyContinue }
        Pop-Location
    }

    $standalone = Join-Path $AdminSrc ".next\standalone"
    if (-not (Test-Path $standalone)) {
        throw "Missing $standalone; is output:standalone set in next.config.mjs?"
    }

    Write-Host "==> Staging admin-ui resources..."
    if (Test-Path $AdminDest) { Remove-Item $AdminDest -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $AdminDest | Out-Null
    Copy-Item -Path (Join-Path $standalone "*") -Destination $AdminDest -Recurse

    $staticSrc = Join-Path $AdminSrc ".next\static"
    if (Test-Path $staticSrc) {
        $staticDest = Join-Path $AdminDest ".next\static"
        New-Item -ItemType Directory -Force -Path (Split-Path $staticDest) | Out-Null
        Copy-Item -Path $staticSrc -Destination $staticDest -Recurse
    }

    $publicSrc = Join-Path $AdminSrc "public"
    if (Test-Path $publicSrc) {
        Copy-Item -Path $publicSrc -Destination (Join-Path $AdminDest "public") -Recurse
    }

    $entry = "server.js"
    $nested = Join-Path $AdminDest "apps\duckclaw-admin\server.js"
    if (Test-Path $nested) { $entry = "apps\duckclaw-admin\server.js" }
    Set-Content -Path (Join-Path $AdminDest "SERVER_ENTRY") -Value $entry -NoNewline
    Write-Host "Admin server entry: $entry"
}

function Stage-NodeRuntime {
    $nodeExe = Join-Path $NodeDest "node.exe"
    if (Test-Path $nodeExe) {
        Write-Host "==> Node runtime already staged at $nodeExe"
        return
    }

    Write-Host "==> Downloading Node v$NodeVersion win-x64..."
    New-Item -ItemType Directory -Force -Path $NodeDest | Out-Null
    $zipUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
    $zipPath = Join-Path $env:TEMP "node-v$NodeVersion-win-x64.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    $extractDir = Join-Path $env:TEMP "node-v$NodeVersion-win-x64"
    if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $env:TEMP -Force
    Copy-Item (Join-Path $extractDir "node.exe") $nodeExe
    Write-Host "Staged $nodeExe"
}

function Copy-SidecarBin {
    $src = Join-Path $RepoRoot "dist\duckclaw_backend.exe"
    $destDir = Join-Path $TauriRoot "bin"
    $dest = Join-Path $destDir "duckclaw_backend-x86_64-pc-windows-msvc.exe"
    if (-not (Test-Path $src)) {
        throw "Missing $src; run scripts/build_desktop_sidecar.ps1 first or omit -SkipSidecar"
    }
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item $src $dest -Force
    Write-Host "Copied sidecar -> $dest"
}

if (-not $SkipSidecar) {
    & (Join-Path $RepoRoot "scripts\build_desktop_sidecar.ps1")
}

Stage-AdminStandalone
Stage-NodeRuntime
Copy-SidecarBin

function Get-GitHubRepoSlug {
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        $slug = gh repo view --json nameWithOwner -q .nameWithOwner 2>$null
        if ($slug) { return $slug.Trim() }
    }
    $remote = git -C $RepoRoot remote get-url origin 2>$null
    if ($remote -match 'github\.com[:/]([^/]+/[^/.]+)') {
        return ($Matches[1] -replace '\.git$', '')
    }
    throw "Cannot resolve GitHub owner/repo from origin remote"
}

function Sync-UpdaterConfig {
    $pubPath = Join-Path $DesktopRoot ".tauri\duckclaw.key.pub"
    $tauriConf = Join-Path $TauriRoot "tauri.conf.json"
    $json = Get-Content $tauriConf -Raw -Encoding UTF8 | ConvertFrom-Json
    $changed = $false

    if (Test-Path $pubPath) {
        $pubkey = (Get-Content $pubPath -Raw).Trim()
        if ($json.plugins.updater.pubkey -ne $pubkey) {
            $json.plugins.updater.pubkey = $pubkey
            $changed = $true
            Write-Host "Synced updater pubkey from $pubPath"
        }
    } else {
        Write-Warning "No Minisign pubkey at $pubPath - run scripts/setup_desktop_signing.ps1 for signed updater builds"
    }

    $endpoint = "https://github.com/$(Get-GitHubRepoSlug)/releases/latest/download/latest.json"
    $current = @($json.plugins.updater.endpoints)[0]
    if ($current -ne $endpoint) {
        $json.plugins.updater.endpoints = @($endpoint)
        $changed = $true
        Write-Host "Synced updater endpoint -> $endpoint"
    }

    if ($changed) {
        $out = $json | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($tauriConf, $out, [System.Text.UTF8Encoding]::new($false))
    }
}

function Set-TauriSigningEnv {
    $keyPath = Join-Path $DesktopRoot ".tauri\duckclaw.key"
    if (-not (Test-Path $keyPath)) {
        Write-Host "==> No Minisign private key; generating..."
        & (Join-Path $RepoRoot "scripts\setup_desktop_signing.ps1")
    }
    if (-not (Test-Path $keyPath)) {
        throw "Missing Minisign private key at $keyPath (run scripts/setup_desktop_signing.ps1)"
    }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
        $env:TAURI_SIGNING_PRIVATE_KEY = (Resolve-Path -LiteralPath $keyPath).Path
    }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
        # ponytail: matches setup_desktop_signing.ps1 dev default; CI should set env explicitly
        $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "duckclaw-dev-signing"
    }
    Write-Host "Updater signing env ready (private key loaded)"
}

if (-not $SkipTauri) {
    Sync-UpdaterConfig
    Set-TauriSigningEnv
}

if (-not $SkipTauri) {
    Write-Host "==> Tauri build..."
    Push-Location $DesktopRoot
    try {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm not found"
        }
        if (-not (Test-Path "node_modules")) { npm install }
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        npm run tauri build
        $ErrorActionPreference = $prevEap
        if ($LASTEXITCODE -ne 0) { throw "tauri build failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    $bundle = Join-Path $TauriRoot "target\release\bundle\nsis"
    Write-Host "Done. Installer: $(Get-ChildItem $bundle -Filter *.exe | Select-Object -ExpandProperty FullName)"
} else {
    Write-Host "SkipTauri set; resources staged under $ResourcesRoot"
}
