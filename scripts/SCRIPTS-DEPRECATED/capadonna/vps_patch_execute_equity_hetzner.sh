#!/usr/bin/env bash
# Parche rápido en VPS Hetzner: equity en POST + hook embebido + reinicio API :8002.
#
# SSH: si 100.75.4.17 hace timeout, usa IP pública Hetzner (el script lo detecta).
# API :8002 debe estar en UFW (el script abre el puerto si hace falta).
#
#   bash scripts/SCRIPTS-DEPRECATED/capadonna/vps_patch_execute_equity_hetzner.sh
#
# Opcional fallback systemd (si IB no devuelve NetLiquidation):
#   export IBKR_EXECUTE_ACCOUNT_EQUITY_USD=955968
#   bash .../vps_patch_execute_equity_hetzner.sh --set-equity-env
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_ROOT="${REMOTE_ROOT:-/root/duckclaw}"
API_HOST="${API_HOST:-http://100.75.4.17:8002}"
if [[ -z "${SSH_TARGET:-}" ]]; then
  # shellcheck disable=SC1090
  eval "$(bash "${SCRIPT_DIR}/vps_ssh_resolve.sh")"
fi
SSH_TARGET="${SSH_TARGET:-root@100.75.4.17}"
BROKER_SRC="${REPO_ROOT}/scripts/SCRIPTS-DEPRECATED/capadonna/broker_execute_signal.py"
OHLCV_SRC="${REPO_ROOT}/services/ibkr-ohlcv-api/ohlcv_market_routes.py"
REMOTE_BROKER="${REMOTE_ROOT}/scripts/capadonna/broker_execute_signal.py"
REMOTE_OHLCV="${REMOTE_ROOT}/services/ibkr-ohlcv-api/ohlcv_market_routes.py"
SET_EQUITY_ENV="${IBKR_EXECUTE_ACCOUNT_EQUITY_USD:-}"

for f in "$BROKER_SRC" "$OHLCV_SRC"; do
  if [[ ! -f "$f" ]]; then
    echo "Falta archivo local: $f" >&2
    exit 1
  fi
done

echo "==> SSH probe ${SSH_TARGET}"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${SSH_TARGET}" "hostname && test -d ${REMOTE_ROOT} && echo REMOTE_ROOT_OK"

echo "==> UFW: permitir :8002 (API ibkr-ohlcv; antes solo 22/4002/5900)"
ssh -o BatchMode=yes "${SSH_TARGET}" \
  'ufw allow 8002/tcp comment "DuckClaw ibkr-ohlcv-api" 2>/dev/null; ufw allow in on tailscale0 to any port 8002 proto tcp 2>/dev/null; true'

echo "==> mkdir remoto"
ssh -o BatchMode=yes "${SSH_TARGET}" "mkdir -p ${REMOTE_ROOT}/scripts/capadonna ${REMOTE_ROOT}/services/ibkr-ohlcv-api"

echo "==> scp broker + ohlcv routes"
scp -o BatchMode=yes -q "$BROKER_SRC" "${SSH_TARGET}:${REMOTE_BROKER}"
scp -o BatchMode=yes -q "$OHLCV_SRC" "${SSH_TARGET}:${REMOTE_OHLCV}"

if [[ "${1:-}" == "--set-equity-env" ]]; then
  if [[ -z "${SET_EQUITY_ENV}" ]]; then
    echo "Define IBKR_EXECUTE_ACCOUNT_EQUITY_USD para --set-equity-env" >&2
    exit 1
  fi
  echo "==> Añadir IBKR_EXECUTE_ACCOUNT_EQUITY_USD a /etc/duckclaw/ibkr-ohlcv.env"
  ssh -o BatchMode=yes "${SSH_TARGET}" bash -s <<REMOTE
set -euo pipefail
ENV_FILE=/etc/duckclaw/ibkr-ohlcv.env
touch "\$ENV_FILE"
grep -v '^IBKR_EXECUTE_ACCOUNT_EQUITY_USD=' "\$ENV_FILE" >"\${ENV_FILE}.tmp" || true
mv "\${ENV_FILE}.tmp" "\$ENV_FILE"
echo "IBKR_EXECUTE_ACCOUNT_EQUITY_USD=${SET_EQUITY_ENV}" >>"\$ENV_FILE"
chmod 600 "\$ENV_FILE"
REMOTE
fi

echo "==> Asegurar OHLCV_EXECUTE_* en env del servicio"
ssh -o BatchMode=yes "${SSH_TARGET}" bash -s <<REMOTE
set -euo pipefail
ENV_FILE=/etc/duckclaw/ibkr-ohlcv.env
touch "\$ENV_FILE"
for kv in \
  "OHLCV_EXECUTE_ORDER_PYTHON=${REMOTE_ROOT}/.venv/bin/python" \
  "OHLCV_EXECUTE_ORDER_SCRIPT=${REMOTE_BROKER}"; do
  key="\${kv%%=*}"
  grep -v "^\${key}=" "\$ENV_FILE" >"\${ENV_FILE}.tmp" || true
  mv "\${ENV_FILE}.tmp" "\$ENV_FILE"
  echo "\$kv" >>"\$ENV_FILE"
done
chmod 600 "\$ENV_FILE"
REMOTE

echo "==> restart capadonna-observability"
ssh -o BatchMode=yes "${SSH_TARGET}" "systemctl daemon-reload && systemctl restart capadonna-observability && sleep 2 && systemctl is-active capadonna-observability"

echo "==> Verificación en VPS"
ssh -o BatchMode=yes "${SSH_TARGET}" bash -s <<'REMOTE'
set -euo pipefail
grep -n account_equity_usd /root/duckclaw/services/ibkr-ohlcv-api/ohlcv_market_routes.py | head -3
grep -n _embedded_account_equity_usd /root/duckclaw/scripts/capadonna/broker_execute_signal.py | head -3
grep -E '^OHLCV_EXECUTE_ORDER_|^IBKR_EXECUTE_ACCOUNT_EQUITY' /etc/duckclaw/ibkr-ohlcv.env 2>/dev/null || true
curl -sfS -m 8 http://127.0.0.1:8002/health && echo
REMOTE

echo ""
echo "==> HTTP desde tu Mac (Tailscale): ${API_HOST}/health"
curl -sfS -m 8 "${API_HOST}/health" && echo || echo "(curl falló — ¿Tailscale activo en Mac?)"

echo ""
echo "Listo. En .env del gateway Mac usa:"
echo "  IBKR_PORTFOLIO_API_URL=${API_HOST}/api/portfolio/summary"
echo "  IBKR_EXECUTE_ORDER_URL=${API_HOST}/api/broker/execute"
