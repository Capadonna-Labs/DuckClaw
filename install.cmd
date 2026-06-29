@echo off
REM DuckClaw dia cero Windows — doble clic o: .\install.cmd
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  DuckClaw - instalacion
echo  ======================
echo.

if not exist "%~dp0pyproject.toml" (
  echo ERROR: Ejecuta install.cmd desde la raiz del repo ^(carpeta con pyproject.toml^).
  echo        Ruta actual: %CD%
  pause
  exit /b 1
)

set "UV_EXE="
set "UV_DIR=%USERPROFILE%\.local\bin"

call :step 1 5 Comprobando uv...
if exist "%UV_DIR%\uv.exe" set "UV_EXE=%UV_DIR%\uv.exe"
if not defined UV_EXE (
  for /f "delims=" %%U in ('where uv 2^>nul') do (
    set "UV_EXE=%%U"
    goto :uv_found
  )
)

:uv_found
if defined UV_EXE goto :uv_ready

call :step 2 5 Instalando uv - puede tardar 1-2 minutos...
where winget >nul 2>&1
if not errorlevel 1 (
  echo        ^> winget install astral-sh.uv
  winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
)
if exist "%UV_DIR%\uv.exe" set "UV_EXE=%UV_DIR%\uv.exe"
if defined UV_EXE goto :uv_ready

echo        ^> descargando instalador Astral...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='Continue'; Write-Host '        [uv] Conectando...'; " ^
  "irm https://astral.sh/uv/install.ps1 | iex; exit $LASTEXITCODE"
if exist "%UV_DIR%\uv.exe" set "UV_EXE=%UV_DIR%\uv.exe"

:uv_ready
if not defined UV_EXE (
  echo.
  echo ERROR: uv no instalado en %UV_DIR%
  echo Cierra esta ventana, abre una nueva y ejecuta install.cmd otra vez.
  pause
  exit /b 1
)

set "PATH=%UV_DIR%;%USERPROFILE%\.cargo\bin;%LOCALAPPDATA%\Programs\uv;%PATH%"
REM PATH de Node/npm/Redis lo completa duckops (toolchain.refresh_session_path) tras uv run
call :step 3 5 uv listo
echo        %UV_EXE%

call :step 4 5 duckops up - prereqs, uv sync, migrate, PM2...
echo.
"%UV_EXE%" run duckops up %*
set "EC=!ERRORLEVEL!"

call :step 5 5 Fin codigo !EC!
if not "!EC!"=="0" (
  echo.
  echo ====================================================
  echo   INSTALACION FALLIDA ^(codigo !EC!^)
  echo ====================================================
  echo.
  echo   Busca arriba el bloque:
  echo     FALLO EN PREREQUISITOS
  echo   o lineas que empiezan con ERROR
  echo.
  echo   Windows - soluciones rapidas:
  echo     Redis:  net start Redis
  echo     Node/PM2/pnpm: cierra ventana y ejecuta install.cmd otra vez
  echo     Si ves FileNotFoundError: falta algo en PATH ^(npm global en %%APPDATA%%\npm^)
  echo     Carpeta: debe existir pyproject.toml en %CD%
  echo.
  pause
)
exit /b !EC!

:step
echo.
echo  [%~1/5] %~3
exit /b 0
