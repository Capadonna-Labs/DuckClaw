#!/usr/bin/env bash
# Despliega ibkr-ohlcv-api en un VPS Hetzner (p. ej. root@100.75.4.17) como systemd
# capadonna-observability en 0.0.0.0:8002. Requiere IB Gateway Docker en :4002 (paper).
#
# Uso desde Windows/Mac (repo DuckClaw):
#   export SSH_TARGET=root@100.75.4.17
#   export IBKR_API_KEY='tu-clave-bearer'
#   bash scripts/capadonna/vps_deploy_ibkr_ohlcv_hetzner.sh
#
# Solo en el VPS (archivos ya en /root/duckclaw):
#   REMOTE_ROOT=/root/duckclaw IBKR_API_KEY='...' bash vps_deploy_ibkr_ohlcv_hetzner.sh --local
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SSH_TARGET="${SSH_TARGET:-root@100.75.4.17}"
REMOTE_ROOT="${REMOTE_ROOT:-/root/duckclaw}"
API_KEY="${IBKR_API_KEY:-${IBKR_PORTFOLIO_API_KEY:-}}"

run_remote_install() {
  REMOTE_ROOT="$1"
  API_KEY="$2"
  export REMOTE_ROOT API_KEY
  bash <<'INSTALL'
set -euo pipefail

echo "=== Dependencias del sistema ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl

echo "=== Venv Python ==="
cd "$REMOTE_ROOT"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r services/ibkr-ohlcv-api/requirements.txt ib_async duckdb pytz pyarrow

echo "=== Entorno del servicio ==="
install -d -m 755 /etc/duckclaw
cat >/etc/duckclaw/ibkr-ohlcv.env <<ENV_EOF
OHLCV_BIND_HOST=0.0.0.0
OHLCV_BIND_PORT=8002
OHLCV_PROJECT_ROOT=${REMOTE_ROOT}
OHLCV_IB_PYTHON=${REMOTE_ROOT}/.venv/bin/python
OHLCV_IB_SCRIPT=${REMOTE_ROOT}/scripts/capadonna/ibkr_historical_bars.py
OHLCV_IB_CLIENT_ID=42
OHLCV_IB_FALLBACK=1
OHLCV_LAKE_PYTHON=${REMOTE_ROOT}/.venv/bin/python
OHLCV_LAKE_SCRIPT=${REMOTE_ROOT}/scripts/export_lake_ohlcv.py
CAPADONNA_LAKE_DATA_ROOT=${REMOTE_ROOT}/data/lake
OHLCV_PORTFOLIO_PYTHON=${REMOTE_ROOT}/.venv/bin/python
OHLCV_PORTFOLIO_SCRIPT=${REMOTE_ROOT}/scripts/capadonna/ibkr_portfolio_snapshot.py
IBKR_SNAPSHOT_CLIENT_ID=999
PORTFOLIO_IB_CLIENT_ID=999
OHLCV_EXECUTE_ORDER_PYTHON=${REMOTE_ROOT}/.venv/bin/python
OHLCV_EXECUTE_ORDER_SCRIPT=${REMOTE_ROOT}/scripts/capadonna/broker_execute_signal.py
BROKER_EXECUTE_CLIENT_ID=47
OHLCV_BROKER_EXECUTE_FORCE_PAPER=1
IB_HOST=127.0.0.1
IB_PORT=4002
IB_ENV=paper
ENV_EOF
if [ -n "${API_KEY:-}" ]; then
  printf 'OHLCV_API_KEY=%s\nIBKR_PORTFOLIO_API_KEY=%s\n' "$API_KEY" "$API_KEY" >>/etc/duckclaw/ibkr-ohlcv.env
fi
chmod 600 /etc/duckclaw/ibkr-ohlcv.env

echo "=== Lake data dirs ==="
install -d -m 755 "${REMOTE_ROOT}/data/lake/daily" "${REMOTE_ROOT}/data/lake/intraday" "${REMOTE_ROOT}/data/lake/gold" "${REMOTE_ROOT}/data/lake/moc"

echo "=== systemd capadonna-observability ==="
cat >/etc/systemd/system/capadonna-observability.service <<UNIT_EOF
[Unit]
Description=DuckClaw IBKR OHLCV API (:8002)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${REMOTE_ROOT}/services/ibkr-ohlcv-api
EnvironmentFile=/etc/duckclaw/ibkr-ohlcv.env
ExecStart=${REMOTE_ROOT}/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8002
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT_EOF

systemctl daemon-reload
systemctl enable capadonna-observability.service
systemctl restart capadonna-observability.service

echo "=== Verificación ==="
sleep 2
systemctl is-active capadonna-observability.service
ss -tlnp | grep ':8002' || true
curl -sfS -m 8 http://127.0.0.1:8002/health && echo
curl -sfS -m 30 "http://127.0.0.1:8002/api/market/ohlcv?ticker=SPY&timeframe=1d&lookback_days=3" | head -c 400 || echo "(OHLCV: journalctl -u capadonna-observability -n 50)"
curl -sfS -m 45 -H "X-Duckclaw-IBKR-Account-Mode: paper" http://127.0.0.1:8002/api/portfolio/summary | head -c 400 || echo "(portfolio: journalctl -u capadonna-observability -n 50)"
INSTALL
}

if [[ "${1:-}" == "--local" ]]; then
  run_remote_install "$REMOTE_ROOT" "$API_KEY"
  exit 0
fi

echo "=== Sincronizando archivos mínimos a ${SSH_TARGET}:${REMOTE_ROOT} ==="
ssh "$SSH_TARGET" "mkdir -p ${REMOTE_ROOT}/services/ibkr-ohlcv-api ${REMOTE_ROOT}/scripts/capadonna ${REMOTE_ROOT}/scripts ${REMOTE_ROOT}/data/lake"
scp -q \
  "$REPO_ROOT/services/ibkr-ohlcv-api/main.py" \
  "$REPO_ROOT/services/ibkr-ohlcv-api/ohlcv_market_routes.py" \
  "$REPO_ROOT/services/ibkr-ohlcv-api/portfolio_routes.py" \
  "$REPO_ROOT/services/ibkr-ohlcv-api/requirements.txt" \
  "${SSH_TARGET}:${REMOTE_ROOT}/services/ibkr-ohlcv-api/"
scp -q \
  "$REPO_ROOT/scripts/capadonna/ibkr_historical_bars.py" \
  "$REPO_ROOT/scripts/capadonna/ibkr_portfolio_snapshot.py" \
  "$REPO_ROOT/scripts/capadonna/broker_execute_signal.py" \
  "$REPO_ROOT/scripts/capadonna/vps_deploy_ibkr_ohlcv_hetzner.sh" \
  "${SSH_TARGET}:${REMOTE_ROOT}/scripts/capadonna/"
scp -q \
  "$REPO_ROOT/scripts/capadonna/export_lake_ohlcv.py" \
  "${SSH_TARGET}:${REMOTE_ROOT}/scripts/"

echo "=== Instalando en el VPS ==="
ssh -t "$SSH_TARGET" "REMOTE_ROOT='${REMOTE_ROOT}' IBKR_API_KEY='${API_KEY}' bash ${REMOTE_ROOT}/scripts/capadonna/vps_deploy_ibkr_ohlcv_hetzner.sh --local"

echo "=== Listo. Prueba: http://100.75.4.17:8002/health ==="
