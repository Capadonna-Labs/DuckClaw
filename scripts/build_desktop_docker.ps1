# Build DuckClaw Full Docker images + optional Windows launcher .exe
# Usage:
#   pwsh scripts/build_desktop_docker.ps1
#   pwsh scripts/build_desktop_docker.ps1 -SkipTauri
#   pwsh scripts/build_desktop_docker.ps1 -ExportTar

param(
    [switch]$SkipTauri,
    [switch]$ExportTar,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Deploy = Join-Path $Root "deploy\docker"
$DesktopDocker = Join-Path $Root "packages\desktop-docker"
if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist\docker-full"
}

Write-Host "==> DuckClaw Full Docker build" -ForegroundColor Cyan
Write-Host "Root: $Root"

Push-Location $Deploy
try {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created deploy/docker/.env from .env.example"
    }
    Write-Host "==> docker compose build (gateway, sandbox slim, admin)"
    $t0 = Get-Date
    docker compose -f docker-compose.yml build gateway sandbox admin
    if ($LASTEXITCODE -ne 0) { throw "docker compose build failed" }
    $buildSec = [int]((Get-Date) - $t0).TotalSeconds
    Write-Host "Image build wall time: ${buildSec}s"
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Copy-Item (Join-Path $Deploy "docker-compose.release.yml") (Join-Path $OutDir "docker-compose.yml") -Force
Copy-Item (Join-Path $Deploy ".env.example") (Join-Path $OutDir ".env.example") -Force
Copy-Item (Join-Path $Deploy "tailscale-serve.json") (Join-Path $OutDir "tailscale-serve.json") -Force

# Sync release compose into Tauri resources
$StackRes = Join-Path $DesktopDocker "src-tauri\resources\stack"
New-Item -ItemType Directory -Force -Path $StackRes | Out-Null
Copy-Item (Join-Path $Deploy "docker-compose.release.yml") (Join-Path $StackRes "docker-compose.yml") -Force
Copy-Item (Join-Path $Deploy ".env.example") (Join-Path $StackRes ".env.example") -Force
Copy-Item (Join-Path $Deploy "tailscale-serve.json") (Join-Path $StackRes "tailscale-serve.json") -Force

if ($ExportTar) {
    $tar = Join-Path $OutDir "duckclaw-full-images.tar"
    Write-Host "==> docker save -> $tar"
    docker save -o $tar duckclaw/gateway:latest duckclaw/admin:latest duckclaw/sandbox:latest redis:7-alpine
    if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
    Write-Host "Saved $tar"
}

if (-not $SkipTauri) {
    Write-Host "==> npm install + tauri build (DuckClaw Full launcher)"
    Push-Location $DesktopDocker
    try {
        if (-not (Test-Path "node_modules")) {
            npm install
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }
        $nsis = Get-ChildItem -Path (Join-Path $DesktopDocker "src-tauri\target\release\bundle\nsis") -Filter "*.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($nsis) {
            Copy-Item $nsis.FullName $OutDir -Force
            Write-Host "Launcher: $($nsis.Name) -> $OutDir"
        } else {
            Write-Warning "NSIS .exe not found; check tauri build output"
        }
    } finally {
        Pop-Location
    }
}

Write-Host "==> Done. Artifacts in $OutDir" -ForegroundColor Green
Write-Host "Smoke CLI: pwsh scripts/smoke_docker_full.ps1"
