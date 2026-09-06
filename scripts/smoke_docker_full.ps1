# Smoke test: DuckClaw Full Docker stack (CLI, no .exe required).
# Measures first-up vs second-up wall time. Expects Docker Desktop running.
# Usage: powershell -File scripts/smoke_docker_full.ps1

param(
    [switch]$SkipRebuild,
    [string]$ReportPath = ""
)

# Docker writes progress to stderr; do not treat as terminating errors.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Deploy = Join-Path $Root "deploy\docker"
if (-not $ReportPath) {
    $ReportPath = Join-Path $Root "docs\deploy\SMOKE_DOCKER_FULL_REPORT.md"
}

function Invoke-Docker([string[]]$DockerArgs) {
    $p = Start-Process -FilePath "docker" -ArgumentList $DockerArgs -Wait -PassThru -NoNewWindow
    if ($null -eq $p) { return 1 }
    return [int]$p.ExitCode
}

function Wait-HttpOk([string]$Url, [string]$Label, [int]$TimeoutSec = 600) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $n = 0
    while ((Get-Date) -lt $deadline) {
        $n++
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -lt 500) {
                Write-Host "OK $Label after ${n} polls"
                return
            }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "Timeout waiting for $Label ($Url)"
}

Write-Host "==> Smoke Docker Full" -ForegroundColor Cyan

$infoCode = Invoke-Docker @("info")
if ($infoCode -ne 0) { throw "Docker Desktop not available" }

Push-Location $Deploy
try {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
    }

    Write-Host "==> compose down (clean volumes for empty DB smoke)"
    [void](Invoke-Docker @("compose", "-f", "docker-compose.yml", "down", "-v"))

    if (-not $SkipRebuild) {
        Write-Host "==> build images"
        $tb = Get-Date
        $bc = Invoke-Docker @("compose", "-f", "docker-compose.yml", "build", "gateway", "sandbox", "admin")
        if ($bc -ne 0) { throw "build failed" }
        $buildSec = [int]((Get-Date) - $tb).TotalSeconds
    } else {
        $buildSec = 0
    }

    Write-Host "==> first compose up -d"
    $t1 = Get-Date
    $uc = Invoke-Docker @("compose", "-f", "docker-compose.yml", "up", "-d")
    if ($uc -ne 0) {
        Invoke-Docker @("compose", "-f", "docker-compose.yml", "logs", "--tail", "80", "gateway") | Out-Host
        throw "compose up failed (exit $uc)"
    }
    Wait-HttpOk "http://127.0.0.1:8000/health" "gateway /health" 900
    Wait-HttpOk "http://127.0.0.1:3001/login" "admin /login" 300
    $firstUpSec = [int]((Get-Date) - $t1).TotalSeconds

    Write-Host "==> container status"
    [void](Invoke-Docker @("compose", "-f", "docker-compose.yml", "ps"))

    $required = @("gateway", "db-writer", "knowledge-indexer", "redis", "admin")
    $psJson = & docker compose -f docker-compose.yml ps --format json 2>$null
    $ps = @($psJson | ForEach-Object { $_ | ConvertFrom-Json })
    foreach ($name in $required) {
        $hit = $ps | Where-Object { $_.Service -eq $name -or $_.Name -like "*$name*" }
        if (-not $hit) { throw "Missing service container: $name" }
    }

    Write-Host "==> login probe (admin page reachable; credentials from .env)"
    $envMap = @{}
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_.Split('=', 2)
        $envMap[$k.Trim()] = $v.Trim()
    }
    $email = $envMap["DUCKCLAW_ADMIN_EMAIL"]
    $pass = $envMap["DUCKCLAW_ADMIN_PASSWORD"]
    if (-not $email -or -not $pass) { throw "Admin credentials missing in .env" }
    Write-Host "Admin email: $email (password length $($pass.Length))"

    Write-Host "==> assert no quant_core in empty vault (duckdb inside gateway)"
    $py = @'
import os
import duckdb
p = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH", "/data/duckclaw.duckdb")
con = duckdb.connect(p, read_only=True)
rows = con.execute(
    "SELECT table_schema||'.'||table_name FROM information_schema.tables "
    "WHERE lower(table_schema) LIKE '%quant%' OR lower(table_name) LIKE '%quant%'"
).fetchall()
print("quant_matches", len(rows))
for r in rows:
    print(r[0])
raise SystemExit(0 if len(rows) == 0 else 2)
'@
    $pyFile = Join-Path $env:TEMP "duckclaw_smoke_quant_check.py"
    Set-Content -Path $pyFile -Value $py -Encoding UTF8
    Get-Content $pyFile | & docker compose -f docker-compose.yml exec -T gateway python -
    if ($LASTEXITCODE -ne 0) { throw "quant_core or quant tables present in base DB" }
    Write-Host "OK no quant schemas in base DB"

    Write-Host "==> second compose up (warm)"
    [void](Invoke-Docker @("compose", "-f", "docker-compose.yml", "stop"))
    $t2 = Get-Date
    [void](Invoke-Docker @("compose", "-f", "docker-compose.yml", "up", "-d"))
    Wait-HttpOk "http://127.0.0.1:8000/health" "gateway /health (2nd)" 180
    Wait-HttpOk "http://127.0.0.1:3001/login" "admin /login (2nd)" 120
    $secondUpSec = [int]((Get-Date) - $t2).TotalSeconds

    $report = @"
# Smoke report — DuckClaw Full Docker

Date: $(Get-Date -Format o)
Host: $env:COMPUTERNAME

## Results

| Check | Result |
|-------|--------|
| Docker Desktop | OK |
| Image build (wall) | ${buildSec}s |
| First ``compose up`` → health | ${firstUpSec}s |
| Second ``compose up`` → health | ${secondUpSec}s |
| gateway /health | OK |
| admin /login | OK |
| Containers (gateway, db-writer, redis, knowledge-indexer, admin) | OK |
| Login credentials present in .env | OK ($email) |
| No quant_core / quant tables in base DB | OK |
| Manual .env / console edits | None required |

## Notes

- Stack path: ``deploy/docker``
- Auth: ``DUCKCLAW_ADMIN_EMAIL`` / ``DUCKCLAW_ADMIN_PASSWORD`` from ``.env``
- Quant-Trader / quant_core intentionally absent (import via worker zip = paso 2)
- Tailscale not required for this smoke (localhost only)

## Verdict

**PASS** — ready for launcher .exe smoke / friend PC after packaging images.
"@
    $reportDir = Split-Path $ReportPath -Parent
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    Set-Content -Path $ReportPath -Value $report -Encoding UTF8
    Write-Host $report
    Write-Host "==> Wrote $ReportPath" -ForegroundColor Green
} finally {
    Pop-Location
}
