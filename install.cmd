@echo off
REM DuckClaw dia cero Windows — doble clic o: install.cmd
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  DuckClaw - instalacion
echo  ======================
echo.

if exist "%~dp0duckops-up.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0duckops-up.ps1" %*
  set "EC=!ERRORLEVEL!"
  if not "!EC!"=="0" pause
  exit /b !EC!
)

where uv >nul 2>&1
if errorlevel 1 (
  echo Instalando uv...
  where winget >nul 2>&1
  if not errorlevel 1 (
    winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
  )
  where uv >nul 2>&1
  if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  )
  set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%LOCALAPPDATA%\Programs\uv;%PATH%"
)

where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo No se encontro uv. Cierra esta ventana, abre una nueva y ejecuta install.cmd otra vez.
  echo.
  pause
  exit /b 1
)

echo duckops up...
uv run duckops up %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" pause
exit /b %EC%
