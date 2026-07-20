@echo off
REM Entrada día cero Windows (doble clic). Implementación: scripts/bootstrap/install.cmd
cd /d "%~dp0"
call scripts\bootstrap\install.cmd %*
exit /b %ERRORLEVEL%
