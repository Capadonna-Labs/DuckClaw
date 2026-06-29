# Dia cero DuckClaw Windows — .\duckops-up.ps1
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DuckOpsArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

function Write-Step([int]$Current, [int]$Total, [string]$Message) {
    $pct = [math]::Min(100, [int](($Current / $Total) * 100))
    Write-Host ""
    Write-Host "  [$Current/$Total] ($pct%) $Message"
}

function Refresh-UserPath {
    try {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($userPath) {
            $env:Path = "$userPath;$env:Path"
        }
    } catch {
        # ignore
    }
}

function Find-UvExe {
    Refresh-UserPath
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe")
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) {
            $dir = Split-Path $path -Parent
            $env:Path = "$dir;$env:Path"
            return $path
        }
    }
    return $null
}

function Install-Uv {
    Write-Step 2 5 "Instalando uv (1-2 min, veras la descarga abajo)..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "        > winget install astral-sh.uv"
        & winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
        Refresh-UserPath
        $found = Find-UvExe
        if ($found) { return $found }
    }
    Write-Host "        > descargando instalador Astral..."
    $ProgressPreference = "Continue"
    irm https://astral.sh/uv/install.ps1 | iex
    Refresh-UserPath
    $found = Find-UvExe
    if (-not $found) {
        $fallback = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        if (Test-Path $fallback) {
            $env:Path = "$(Split-Path $fallback -Parent);$env:Path"
            return $fallback
        }
        throw "uv no encontrado tras instalar. Cierra PowerShell, abre una nueva y ejecuta .\install.cmd"
    }
    return $found
}

if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    throw "Ejecuta desde la raiz del repo (carpeta con pyproject.toml). Actual: $RepoRoot"
}

Write-Step 1 5 "Comprobando uv..."
$uvExe = Find-UvExe
if (-not $uvExe) {
    $uvExe = Install-Uv
}

Write-Step 3 5 "uv listo"
Write-Host "        $uvExe"

Write-Step 4 5 "duckops up (prereqs, uv sync, migrate, PM2)..."
Write-Host ""
& $uvExe run duckops up @DuckOpsArgs
$code = $LASTEXITCODE

Write-Step 5 5 "Fin (codigo $code)"
exit $code
