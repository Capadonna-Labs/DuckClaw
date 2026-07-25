# Build DuckClaw desktop sidecar (PyInstaller, console first)
#
# Prereq: uv sync (dev group includes pyinstaller). This repo's .venv has no pip.
#
# Smoke after build:
#   1. dist\duckclaw_backend.exe  (or: uv run python services/desktop-sidecar/run.py)
#   2. GET http://127.0.0.1:8000/health
#   3. Stop process cleanly
#
# Spec: docs/specs/features/platform/DESKTOP_LITE_SIDECAR.md

param(
    [switch]$SmokeOnly,
    [int]$Port = 8000,
    [int]$SmokeTimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Invoke-SidecarSmoke {
    param(
        [string]$BaseUrl = "http://127.0.0.1:$Port"
    )
    $deadline = (Get-Date).AddSeconds($SmokeTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                Write-Host "Smoke OK: $($resp.Content)"
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Smoke failed: no /health on $BaseUrl within ${SmokeTimeoutSec}s"
}

function Ensure-PyInstaller {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv not found. Install uv, then run: uv sync"
    }
    Write-Host "Syncing dev deps (pyinstaller)..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv sync --group dev 2>&1 | Out-Null
    } else {
        throw "uv not found. Install uv, then run: uv sync --group dev"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed (exit $LASTEXITCODE)"
    }
}

function Invoke-PyInstallerBuild {
    param([string]$SpecPath)
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run pyinstaller $SpecPath --noconfirm --clean
    } else {
        $venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        $python = if (Test-Path $venvPy) { $venvPy } else { "python" }
        & $python -m PyInstaller $SpecPath --noconfirm --clean
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed (exit $LASTEXITCODE)"
    }
}

if ($SmokeOnly) {
    Invoke-SidecarSmoke
    exit 0
}

Ensure-PyInstaller

$spec = Join-Path $RepoRoot "services\desktop-sidecar\duckclaw_sidecar.spec"
Write-Host "Building $spec ..."
Invoke-PyInstallerBuild -SpecPath $spec

$exe = Join-Path $RepoRoot "dist\duckclaw_backend.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: $exe not found"
}

Write-Host "Built: $exe"
Write-Host "Starting smoke test..."
$env:LITE_MODE = "1"
$env:DUCKCLAW_GATEWAY_PORT = "$Port"
$proc = Start-Process -FilePath $exe -PassThru -NoNewWindow
try {
    Invoke-SidecarSmoke
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Build + smoke complete."
