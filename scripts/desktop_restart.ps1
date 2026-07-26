# Reinicia duckclaw_backend.exe en desktop lite (sin PM2 ni duckops).
$ErrorActionPreference = "Stop"
$exe = Join-Path $env:LOCALAPPDATA "DuckClaw\duckclaw_backend.exe"
$envFile = Join-Path $env:LOCALAPPDATA "DuckClaw\desktop.env"

if (-not (Test-Path $exe)) {
  Write-Error "No encontrado: $exe"
}

Write-Host "Deteniendo duckclaw_backend..."
taskkill /F /IM duckclaw_backend.exe 2>$null | Out-Null
Start-Sleep -Seconds 1

if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
      [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
  }
}

$env:LITE_MODE = "1"
$env:DUCKCLAW_DISABLE_DOTENV = "1"

Write-Host "Arrancando $exe"
Start-Process -FilePath $exe -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) {
      Write-Host "Gateway OK: http://127.0.0.1:8000/health"
      exit 0
    }
  } catch { }
  Start-Sleep -Seconds 2
}

Write-Error "Gateway no respondió en :8000"
