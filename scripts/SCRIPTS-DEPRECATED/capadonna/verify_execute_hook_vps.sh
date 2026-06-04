#!/usr/bin/env bash
# Verifica hook de ejecución en VPS (Hetzner por defecto: root@100.75.4.17).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_ROOT="${REMOTE_ROOT:-/root/duckclaw}"
API_HOST="${API_HOST:-http://100.75.4.17:8002}"
API_HOST_PUBLIC="${API_HOST_PUBLIC:-http://87.99.156.231:8002}"
TOKEN="${IBKR_PORTFOLIO_API_KEY:-${IBKR_ORDER_API_KEY:-}}"
if [[ -z "${SSH_TARGET:-}" ]]; then
  if eval "$(bash "${SCRIPT_DIR}/vps_ssh_resolve.sh" 2>/dev/null)"; then
    :
  else
    SSH_TARGET="${VPS:-root@87.99.156.231}"
    echo "SSH: usando fallback ${SSH_TARGET} (Tailscale SSH no respondió)" >&2
  fi
fi
SSH_TARGET="${SSH_TARGET:-${VPS:-root@87.99.156.231}}"

echo "==> HTTP: ${API_HOST}/health (Tailscale)"
code_ts=$(curl -sS -m 8 -o /tmp/duckclaw_vps_health_ts.json -w "%{http_code}" "${API_HOST}/health" 2>/dev/null || echo "000")
echo "health Tailscale HTTP ${code_ts}"
if [[ "${code_ts}" != "200" ]]; then
  echo "==> HTTP: ${API_HOST_PUBLIC}/health (IP pública — si falla Tailscale, usa esta URL en .env)"
  code_pub=$(curl -sS -m 8 -o /tmp/duckclaw_vps_health_pub.json -w "%{http_code}" "${API_HOST_PUBLIC}/health" 2>/dev/null || echo "000")
  echo "health public HTTP ${code_pub}"
fi

echo ""
echo "==> SSH: ${SSH_TARGET}"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${SSH_TARGET}" \
  "hostname; systemctl is-active capadonna-observability 2>/dev/null || echo service_inactive"

echo ""
echo "==> SSH: /etc/duckclaw/ibkr-ohlcv.env (execute + equity)"
ssh -o BatchMode=yes "${SSH_TARGET}" \
  'grep -E "^OHLCV_EXECUTE_ORDER_|^IBKR_EXECUTE_ACCOUNT_EQUITY" /etc/duckclaw/ibkr-ohlcv.env 2>/dev/null || echo "(sin env file)"'

echo ""
echo "==> SSH: account_equity_usd en ohlcv_market_routes.py"
ssh -o BatchMode=yes "${SSH_TARGET}" \
  "grep -n account_equity_usd ${REMOTE_ROOT}/services/ibkr-ohlcv-api/ohlcv_market_routes.py 2>/dev/null | head -5 || echo '(falta — ejecuta vps_patch_execute_equity_hetzner.sh)'"

echo ""
echo "==> SSH: _embedded_account_equity_usd en broker hook"
ssh -o BatchMode=yes "${SSH_TARGET}" \
  "grep -n _embedded_account_equity_usd ${REMOTE_ROOT}/scripts/capadonna/broker_execute_signal.py 2>/dev/null | head -3 || echo '(falta — ejecuta vps_patch_execute_equity_hetzner.sh)'"

if [[ -n "${TOKEN}" ]]; then
  echo "==> HTTP: portfolio summary"
  code=$(curl -sS -m 12 -o /tmp/duckclaw_vps_portfolio.json -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "X-Duckclaw-IBKR-Account-Mode: paper" \
    "${API_HOST}/api/portfolio/summary" 2>/dev/null || echo "000")
  echo "portfolio HTTP ${code}"
  if [[ "${code}" == "200" ]]; then
    python3 -c "import json; d=json.load(open('/tmp/duckclaw_vps_portfolio.json')); print('net_liquidation', d.get('net_liquidation') or d.get('total_value'))" 2>/dev/null || true
  fi
fi

echo ""
echo "Si algo falta: bash scripts/SCRIPTS-DEPRECATED/capadonna/vps_patch_execute_equity_hetzner.sh"
