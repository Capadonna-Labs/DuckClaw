# Día cero DuckClaw — instala uv si falta y ejecuta duckops up.
# Uso: .\duckops-up.ps1 [flags de duckops up]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DuckOpsArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

function Write-DuckLog([string]$Message) {
    Write-Host "🦆 $Message"
}

function Find-UvExe {
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
    Write-DuckLog "Instalando uv (Astral)..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
        $found = Find-UvExe
        if ($found) { return $found }
    }
    irm https://astral.sh/uv/install.ps1 | iex
    $found = Find-UvExe
    if (-not $found) {
        throw "uv no está en PATH tras la instalación. Cierra y reabre PowerShell, luego ejecuta de nuevo .\duckops-up.ps1"
    }
    return $found
}

$uvExe = Find-UvExe
if (-not $uvExe) {
    $uvExe = Install-Uv
}

Write-DuckLog "duckops up (uv: $uvExe) …"
& $uvExe run duckops up @DuckOpsArgs
exit $LASTEXITCODE
