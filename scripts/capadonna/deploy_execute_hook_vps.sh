#!/usr/bin/env bash
# Copia el hook al VPS y (opcional) la bóveda DuckDB; muestra el bloque systemd (drop-in).
#
# Si el gateway envía siempre POST enriquecido a IBKR_EXECUTE_ORDER_URL, puedes omitir la copia del .duckdb:
#   export SKIP_DUCKDB_COPY=1
#
# Uso (con fallback DB en el VPS):
#   export VPS=capadonna@100.97.151.69
#   export LOCAL_DUCKDB="/ruta/local/a/tu.boveda.duckdb"
#   ./scripts/capadonna/deploy_execute_hook_vps.sh
#
# Uso (solo script + hook; sin IBKR_EXECUTE_ORDER_DB_PATH en el drop-in):
#   export VPS=capadonna@100.97.151.69
#   export SKIP_DUCKDB_COPY=1
#   ./scripts/capadonna/deploy_execute_hook_vps.sh
#
# Luego en el VPS (con sudo):
#   sudo tee /etc/systemd/system/capadonna-observability.service.d/99-execute-order.conf <<'EOF'
#   ... (el script imprime el contenido sugerido)
#   sudo systemctl daemon-reload && sudo systemctl restart capadonna-observability

set -euo pipefail

VPS="${VPS:-capadonna@100.97.151.69}"
REMOTE_DIR="${REMOTE_DIR:-/home/capadonna/var/duckclaw_execute}"
REMOTE_DB="${REMOTE_DB:-${REMOTE_DIR}/vault.duckdb}"
LOCAL_DUCKDB="${LOCAL_DUCKDB:-}"
SKIP_DUCKDB_COPY="${SKIP_DUCKDB_COPY:-}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_SRC="${ROOT}/scripts/capadonna/broker_execute_signal.py"

if [[ -z "${SKIP_DUCKDB_COPY}" ]]; then
  if [[ -z "${LOCAL_DUCKDB}" ]]; then
    echo "Defina LOCAL_DUCKDB con la ruta absoluta al .duckdb del gateway (ej. db/private/.../algo.duckdb)" >&2
    echo "O export SKIP_DUCKDB_COPY=1 si solo despliegas el script (POST enriquecido desde el gateway)." >&2
    exit 1
  fi
  if [[ ! -f "${LOCAL_DUCKDB}" ]]; then
    echo "No existe el archivo: ${LOCAL_DUCKDB}" >&2
    exit 1
  fi
fi
if [[ ! -f "${SCRIPT_SRC}" ]]; then
  echo "No se encuentra ${SCRIPT_SRC}" >&2
  exit 1
fi

echo "==> ssh ${VPS} mkdir -p ${REMOTE_DIR}"
ssh -o BatchMode=yes "${VPS}" "mkdir -p ${REMOTE_DIR}"

echo "==> scp DuckDB"
scp -o BatchMode=yes "${LOCAL_DUCKDB}" "${VPS}:${REMOTE_DB}"

echo "==> scp broker_execute_signal.py"
scp -o BatchMode=yes "${SCRIPT_SRC}" "${VPS}:${REMOTE_DIR}/broker_execute_signal.py"

PY_REMOTE="/home/capadonna/projects/Capadonna-Driller/.venv/bin/python"
SCRIPT_REMOTE="${REMOTE_DIR}/broker_execute_signal.py"

echo ""
echo "=== Añade esto con sudo en el VPS (drop-in systemd) ==="
if [[ -z "${SKIP_DUCKDB_COPY}" ]]; then
  cat <<EOF
[Service]
Environment=OHLCV_EXECUTE_ORDER_PYTHON=${PY_REMOTE}
Environment=OHLCV_EXECUTE_ORDER_SCRIPT=${SCRIPT_REMOTE}
Environment=IBKR_EXECUTE_ORDER_DB_PATH=${REMOTE_DB}
# Opcional si NetLiquidation no llega a tiempo: equity USD para sizing (paper/live)
# Environment=IBKR_EXECUTE_ACCOUNT_EQUITY_USD=100000
EOF
else
  cat <<EOF
[Service]
Environment=OHLCV_EXECUTE_ORDER_PYTHON=${PY_REMOTE}
Environment=OHLCV_EXECUTE_ORDER_SCRIPT=${SCRIPT_REMOTE}
# Sin IBKR_EXECUTE_ORDER_DB_PATH: el hook usa solo DUCKCLAW_EMBEDDED_EXECUTE_JSON del POST enriquecido.
# Añade la línea siguiente si quieres fallback leyendo finance_worker en DuckDB local:
# Environment=IBKR_EXECUTE_ORDER_DB_PATH=${REMOTE_DB}
# Opcional: Environment=IBKR_EXECUTE_ACCOUNT_EQUITY_USD=100000
EOF
fi
echo ""
echo "Archivo sugerido: /etc/systemd/system/capadonna-observability.service.d/99-execute-order.conf"
echo "Luego: sudo systemctl daemon-reload && sudo systemctl restart capadonna-observability"
echo ""
echo "En el Mac, el .env del gateway solo necesita IBKR_EXECUTE_ORDER_URL e IBKR_PORTFOLIO_API_URL;"
echo "IBKR_EXECUTE_ORDER_DB_PATH en el Mac no lo usa el proceso remoto del hook (solo el VPS, y solo como fallback)."
