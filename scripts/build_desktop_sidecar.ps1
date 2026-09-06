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
    [switch]$SkipBuild,
    [int]$Port = 8000,
    [int]$SmokeTimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Test-GatewayHealth {
    param([string]$BaseUrl = "http://127.0.0.1:$Port")
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-PortInUse {
    param([int]$P = 8000)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $P)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Test-PortBindable {
    # ponytail: connect-test alone misses Windows-excluded ranges (Hyper-V/Docker NAT
    # reserve chunks of the ephemeral range, often starting at 49152) — nothing answers
    # there so Test-PortInUse says "free", but binding fails with WinError 10013.
    param([int]$P)
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, $P)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

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

function Get-FreeLoopbackPort {
    # ponytail: Hyper-V/Docker NAT can reserve several back-to-back chunks starting right
    # at 49152 (seen: 49152-49351 as two consecutive 100-port blocks on one dev machine) —
    # 2000 attempts gives enough runway to walk past multiple such blocks.
    param([int]$Start = 49152, [int]$Attempts = 2000)
    for ($p = $Start; $p -lt ($Start + $Attempts); $p++) {
        if (Test-PortBindable -P $p) { return $p }
    }
    throw "No free loopback port for isolated smoke (tried $Start..$($Start + $Attempts - 1))"
}

function Invoke-IsolatedSidecarSmoke {
    param([string]$ExePath)
    $smokePort = Get-FreeLoopbackPort
    $smokeRoot = Join-Path $env:TEMP "duckclaw-sidecar-smoke-$([guid]::NewGuid().ToString('n').Substring(0, 8))"
    $smokeDb = Join-Path $smokeRoot "smoke.duckdb"
    New-Item -ItemType Directory -Path (Split-Path $smokeDb) -Force | Out-Null

    Write-Host "Port $Port busy (DuckClaw likely running). Isolated smoke on :$smokePort with temp DB..."

    $prevPort = $env:DUCKCLAW_GATEWAY_PORT
    $prevDb = $env:DUCKCLAW_GATEWAY_DB_PATH
    $env:LITE_MODE = "1"
    $env:DUCKCLAW_GATEWAY_PORT = "$smokePort"
    $env:DUCKCLAW_GATEWAY_DB_PATH = $smokeDb

    $proc = Start-Process -FilePath $ExePath -PassThru -NoNewWindow
    try {
        Start-Sleep -Milliseconds 800
        if ($proc.HasExited) {
            throw "Sidecar exited before smoke (code $($proc.ExitCode)). See traceback above."
        }
        Invoke-SidecarSmoke -BaseUrl "http://127.0.0.1:$smokePort"
        if ($proc.HasExited) {
            throw "Sidecar exited during smoke; /health on :$smokePort may be a stale process."
        }
    } finally {
        if (-not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        if ($prevPort) { $env:DUCKCLAW_GATEWAY_PORT = $prevPort } else { Remove-Item Env:DUCKCLAW_GATEWAY_PORT -ErrorAction SilentlyContinue }
        if ($prevDb) { $env:DUCKCLAW_GATEWAY_DB_PATH = $prevDb } else { Remove-Item Env:DUCKCLAW_GATEWAY_DB_PATH -ErrorAction SilentlyContinue }
        Remove-Item -Recurse -Force $smokeRoot -ErrorAction SilentlyContinue
    }
}

function Ensure-PyInstaller {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv not found. Install uv, then run: uv sync"
    }
    Write-Host "Syncing dev deps (pyinstaller)..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & uv sync --group dev 2>&1 | Out-Null
        $ErrorActionPreference = $prevEap
    } else {
        throw "uv not found. Install uv, then run: uv sync --group dev"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed (exit $LASTEXITCODE)"
    }
}

function Stop-DistSidecarProcesses {
    param([string]$ExePath)
    $target = [System.IO.Path]::GetFullPath($ExePath).ToLowerInvariant()
    $stopped = @()
    foreach ($p in Get-Process duckclaw_backend -ErrorAction SilentlyContinue) {
        if (-not $p.Path) { continue }
        if ([System.IO.Path]::GetFullPath($p.Path).ToLowerInvariant() -ne $target) { continue }
        Write-Host "Stopping dist sidecar PID $($p.Id) (locks rebuild)..."
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        $stopped += $p.Id
    }
    if ($stopped.Count -gt 0) {
        Start-Sleep -Milliseconds 800
    }
}

function Invoke-PyInstallerBuild {
    param([string]$SpecPath, [string]$DistExe)
    Stop-DistSidecarProcesses -ExePath $DistExe
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run pyinstaller $SpecPath --noconfirm --clean
    } else {
        $venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        $python = if (Test-Path $venvPy) { $venvPy } else { "python" }
        & $python -m PyInstaller $SpecPath --noconfirm --clean
    }
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed (exit $LASTEXITCODE)"
    }
}

if ($SmokeOnly) {
    Invoke-SidecarSmoke
    exit 0
}

$exe = Join-Path $RepoRoot "dist\duckclaw_backend.exe"
if (-not $SkipBuild) {
    Ensure-PyInstaller

    $spec = Join-Path $RepoRoot "services\desktop-sidecar\duckclaw_sidecar.spec"
    Write-Host "Building $spec ..."
    Invoke-PyInstallerBuild -SpecPath $spec -DistExe $exe

    if (-not (Test-Path $exe)) {
        throw "Build failed: $exe not found"
    }
    Write-Host "Built: $exe"
} elseif (-not (Test-Path $exe)) {
    throw "SkipBuild set but $exe not found"
} else {
    Write-Host "SkipBuild: using existing $exe"
}

Write-Host "Starting smoke test..."
$healthOk = Test-GatewayHealth -BaseUrl "http://127.0.0.1:$Port"
$portBusy = Test-PortInUse -P $Port
if ($healthOk -or $portBusy) {
    if (Test-PortInUse -P $Port) {
        Write-Host "Port $Port busy; using isolated smoke port."
    }
    Invoke-IsolatedSidecarSmoke -ExePath $exe
} else {
    $env:LITE_MODE = "1"
    $env:DUCKCLAW_GATEWAY_PORT = "$Port"
    Remove-Item Env:DUCKCLAW_GATEWAY_DB_PATH -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $exe -PassThru -NoNewWindow
    try {
        Start-Sleep -Milliseconds 800
        if ($proc.HasExited) {
            throw "Sidecar exited before smoke (code $($proc.ExitCode))."
        }
        Invoke-SidecarSmoke
    } finally {
        if (-not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Build + smoke complete."
