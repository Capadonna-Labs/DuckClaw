#!/usr/bin/env bash
# ML4T batch sobre DuckDB (solo lectura, red desactivada). No usa ml4t-data —
# serie desde quant_core.ingesta DuckClaw existente.
#
# Ejemplos:
#   DUCKDB_PATH=/abs/vault.duckdb ./scripts/quant/run_ml4t_batch_docker.sh diagnostics --tickers SPY,TLT,IEF
#   DUCKDB_PATH=/abs/vault.duckdb ./scripts/quant/run_ml4t_batch_docker.sh backtest --tickers SPY,XLU --max-rows-per-ticker 252
#
# Requiere: imagen duckclaw/sandbox:latest (docker build docker/sandbox) o STRIX_SANDBOX_IMAGE.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMG="${STRIX_SANDBOX_IMAGE:-duckclaw/sandbox:latest}"
BIND_SCRIPTS="$REPO/scripts/quant"

DB_HOST="${DUCKDB_PATH:-${DUCKCLAW_QUANT_SCRIPT_DB:-}}"
MODE="${1:-diagnostics}"
shift || true

if [[ -z "$DB_HOST" ]]; then
  echo "Define DUCKDB_PATH o DUCKCLAW_QUANT_SCRIPT_DB (ruta al .duckdb en el host)" >&2
  exit 2
fi
DB_HOST_EXPAND="${DB_HOST/#\~/$HOME}"
DB_HOST_EXPAND="$(python3 -c "import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve())" "$DB_HOST_EXPAND")"
[[ -f "$DB_HOST_EXPAND" ]] || { echo "Archivo DuckDB no encontrado: $DB_HOST_EXPAND" >&2; exit 2; }

case "$MODE" in
  diagnostics)
    ENTRY="ml4t_batch_diagnostics.py"
    ;;
  backtest)
    ENTRY="ml4t_batch_backtest.py"
    ;;
  *)
    echo "Uso: $0 diagnostics|backtest [--duckdb-path /duck/ro.duckdb] ..." >&2
    echo "  Las opciones después del modo pasan al script Python (incluye --tickers)." >&2
    exit 2
    ;;
esac

INSIDE_DB="/duckclaw/ro_vault.duckdb"
exec docker run --rm \
  --network none \
  -v "$DB_HOST_EXPAND:$INSIDE_DB:ro" \
  -v "$BIND_SCRIPTS:/duckscripts:ro" \
  -e ML4T_DSR_TRIALS="${ML4T_DSR_TRIALS:-50}" \
  -e ML4T_DSR_BENCH="${ML4T_DSR_BENCH:-0}" \
  "$IMG" \
  python "/duckscripts/$ENTRY" --duckdb-path "$INSIDE_DB" "$@"