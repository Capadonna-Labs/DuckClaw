@echo off
REM Stop infinite black console windows on Windows.
REM Causes: PM2 admin-ui CMD crash-loop, python.exe consoles on gateway/db-writer restart.

echo [%DATE% %TIME%] kill_console_storm

echo [1/4] Remove PM2 admin-ui (CMD crash-loop source)...
call pm2 delete duckclaw-admin-ui 2>nul

echo [2/4] Stop PM2 python services (each restart = black window)...
call pm2 stop duckclaw-gateway 2>nul
call pm2 stop DuckClaw-DB-Writer 2>nul
call pm2 save 2>nul

echo [3/4] Kill sidecar orphans...
taskkill /F /IM duckclaw_backend.exe 2>nul

echo [4/4] Kill orphan duckclaw python consoles...
for /f "tokens=2" %%p in ('wmic process where "CommandLine like '%%duckclaw%%' and Name='python.exe'" get ProcessId 2^>nul ^| findstr /r "[0-9]"') do taskkill /F /PID %%p 2>nul

echo.
echo Done. Close leftover black windows with X if any remain.
echo To restart stack safely: pm2 start config/ecosystem.spawn.config.cjs --only duckclaw-gateway
echo                         pm2 start config/ecosystem.db-writer.config.cjs
pause
