#!/usr/bin/env pwsh
# Generate Minisign keypair for Tauri updater and inject pubkey into tauri.conf.json.
# Private key: packages/desktop/.tauri/duckclaw.key (gitignored)
# Public key:  packages/desktop/.tauri/duckclaw.key.pub (committed)

param(
    [string]$Password = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot "packages\desktop"
$TauriConf = Join-Path $DesktopRoot "src-tauri\tauri.conf.json"
$KeyDir = Join-Path $DesktopRoot ".tauri"
$KeyPath = Join-Path $KeyDir "duckclaw.key"
$PubPath = "$KeyPath.pub"

New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null

if ((Test-Path $KeyPath) -and -not $Force) {
    Write-Host "Key exists: $KeyPath (use -Force to regenerate)"
} else {
    Push-Location $DesktopRoot
    try {
        if (-not (Test-Path "node_modules")) { npm install }
        $args = @("signer", "generate", "-w", $KeyPath)
        if ($Force) { $args += "-f" }
        if ($Password) {
            $args += @("--password", $Password)
        } else {
            # ponytail: dev-only default; override with -Password in CI
            $args += @("--password", "duckclaw-dev-signing")
        }
        & npx tauri @args
        if ($LASTEXITCODE -ne 0) { throw "tauri signer generate failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $PubPath)) {
    throw "Missing public key: $PubPath"
}

$pubkey = (Get-Content $PubPath -Raw).Trim()
if (-not $pubkey) { throw "Empty pubkey in $PubPath" }

$conf = Get-Content $TauriConf -Raw | ConvertFrom-Json
$conf.plugins.updater.pubkey = $pubkey
$json = $conf | ConvertTo-Json -Depth 20 -Compress:$false
[System.IO.File]::WriteAllText($TauriConf, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Injected pubkey into $TauriConf"
Write-Host "Keep $KeyPath private. Set TAURI_SIGNING_PRIVATE_KEY in CI for release builds."
