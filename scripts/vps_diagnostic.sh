#!/usr/bin/env bash
# Diagnóstico del estado del VPS de producción DuckClaw
# Ejecutar en el VPS: bash scripts/vps_diagnostic.sh

set -euo pipefail

echo "═══════════════════════════════════════════════════"
echo "  DuckClaw VPS Production Diagnostic"
echo "═══════════════════════════════════════════════════"
echo ""

# 1. Sistema
echo "▶ Sistema y Recursos"
echo "────────────────────────────────────────────────────"
uname -a
uptime
free -h
df -h / | tail -1
echo ""

# 2. PM2 Status
echo "▶ PM2 Processes"
echo "────────────────────────────────────────────────────"
pm2 jlist 2>/dev/null | jq -r '.[] | "\(.name): \(.pm2_env.status) (uptime: \(.pm2_env.pm_uptime // 0 | . / 1000 / 60 | floor)m, mem: \(.monit.memory / 1024 / 1024 | floor)MB, cpu: \(.monit.cpu)%)"' || pm2 status
echo ""

# 3. Gateway Health
echo "▶ Gateway Health Check"
echo "────────────────────────────────────────────────────"
source .env 2>/dev/null || true
GATEWAY_URL="${DUCKCLAW_GATEWAY_URL:-http://127.0.0.1:8000}"
curl -s "${GATEWAY_URL}/health" | jq '.' 2>/dev/null || curl -s "${GATEWAY_URL}/health" || echo "Gateway health check failed"
echo ""

# 4. DB Writer Queue
echo "▶ DB Writer Queue Status"
echo "────────────────────────────────────────────────────"
if command -v redis-cli &> /dev/null; then
  REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
  redis-cli -u "${REDIS_URL}" LLEN duckdb_write_queue 2>/dev/null || echo "Redis not accessible"
else
  echo "redis-cli not installed"
fi
echo ""

# 5. DuckDB Size
echo "▶ DuckDB Database Size"
echo "────────────────────────────────────────────────────"
DB_PATH="${DUCKCLAW_GATEWAY_DB_PATH:-db/private/default/duckclaw.duckdb}"
if [ -f "${DB_PATH}" ]; then
  du -h "${DB_PATH}"
  echo "Last modified: $(stat -c %y "${DB_PATH}" 2>/dev/null || stat -f %Sm "${DB_PATH}" 2>/dev/null)"
else
  echo "DB not found at ${DB_PATH}"
fi
echo ""

# 6. Recent Logs (últimas 10 líneas de cada proceso)
echo "▶ Recent PM2 Logs"
echo "────────────────────────────────────────────────────"
for proc in DuckClaw-Gateway DuckClaw-DB-Writer DuckClaw-Heartbeat duckclaw-admin-ui; do
  echo "--- ${proc} (last 5 lines) ---"
  pm2 logs "${proc}" --lines 5 --nostream --raw 2>/dev/null | tail -5 || echo "No logs for ${proc}"
  echo ""
done

# 7. Disk Space por directorio grande
echo "▶ Large Directories"
echo "────────────────────────────────────────────────────"
du -sh db/ ML_models/ results/ conversation_traces/ 2>/dev/null | sort -rh || echo "Directories not found"
echo ""

# 8. Git Status
echo "▶ Git Repository Status"
echo "────────────────────────────────────────────────────"
git log --oneline -1
git status --short | head -10
echo ""

# 9. Python/Node versions
echo "▶ Runtime Versions"
echo "────────────────────────────────────────────────────"
python3 --version 2>/dev/null || echo "Python3 not found"
uv --version 2>/dev/null || echo "uv not found"
node --version 2>/dev/null || echo "Node not found"
pnpm --version 2>/dev/null || echo "pnpm not found"
pm2 --version 2>/dev/null || echo "PM2 not found"
echo ""

# 10. Network
echo "▶ Network Connectivity"
echo "────────────────────────────────────────────────────"
curl -s --max-time 3 https://api.openrouter.ai/api/v1/models 2>&1 | head -c 100 && echo "... [OpenRouter OK]" || echo "OpenRouter: FAILED"
tailscale status 2>/dev/null | head -5 || echo "Tailscale not available"
echo ""

echo "═══════════════════════════════════════════════════"
echo "  Diagnostic Complete"
echo "═══════════════════════════════════════════════════"
