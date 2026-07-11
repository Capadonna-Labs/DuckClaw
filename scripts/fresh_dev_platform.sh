#!/usr/bin/env bash
# Fresh DuckClaw dev vault — usuario nuevo, bóveda default limpia.
# Uso: bash scripts/fresh_dev_platform.sh
# Requiere: .env con DUCKCLAW_GATEWAY_DB_PATH=db/private/default/duckclaw.duckdb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

if [[ ! -f .env ]]; then
  echo "error: falta .env en $ROOT" >&2
  exit 1
fi

VAULT="${DUCKCLAW_GATEWAY_DB_PATH:-db/private/default/duckclaw.duckdb}"
# shellcheck disable=SC1091
set -a && source .env && set +a
VAULT="${DUCKCLAW_GATEWAY_DB_PATH:-db/private/default/duckclaw.duckdb}"

echo "==> Deteniendo stack PM2 (libera locks DuckDB)…"
uv run duckops stack down 2>/dev/null || true

echo "==> Eliminando bóveda anterior: $VAULT"
rm -f "$VAULT" "${VAULT}.wal" 2>/dev/null || true

echo "==> Opcional: migrar vaults legacy axis.duckdb → duckclaw.duckdb…"
echo "    bash scripts/migrate_legacy_axis_vault.sh"
if [[ -d db/private/7822026745 ]]; then
  rm -rf db/private/7822026745
  echo "    eliminado db/private/7822026745/"
fi

echo "==> Migraciones + seed admin (duckclaw-migrate)…"
uv run duckclaw-migrate

echo "==> Deploy stack PM2…"
uv run duckops stack deploy

echo "==> Verificación post-deploy…"
uv run duckclaw-healthcheck || echo "warn: healthcheck pendiente — revisa pm2 logs DuckClaw-Gateway"

echo ""
echo "✓ Plataforma lista (usuario nuevo)"
echo "  Vault: $VAULT"
echo "  Admin: cd apps/duckclaw-admin && pnpm dev"
echo "  Login: credenciales DUCKCLAW_ADMIN_EMAIL / DUCKCLAW_ADMIN_PASSWORD en .env"
