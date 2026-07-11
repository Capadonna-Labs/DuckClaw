#!/usr/bin/env bash
# Renombra bóvedas legacy axis.duckdb → duckclaw.duckdb y limpia DUCKCLAW_AXIS_DB_PATH del .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

renamed=0
while IFS= read -r -d '' legacy; do
  target="${legacy%/axis.duckdb}/duckclaw.duckdb"
  if [[ -f "$target" ]]; then
    echo "SKIP (dest exists): $legacy"
    continue
  fi
  mv "$legacy" "$target"
  echo "RENAMED: $legacy -> $target"
  renamed=$((renamed + 1))
done < <(find db -name 'axis.duckdb' -type f -print0 2>/dev/null || true)

if [[ -f .env ]]; then
  if grep -q 'DUCKCLAW_AXIS_DB_PATH' .env; then
    tmp="$(mktemp)"
    grep -v 'DUCKCLAW_AXIS_DB_PATH' .env >"$tmp" || true
    mv "$tmp" .env
    echo "Removed DUCKCLAW_AXIS_DB_PATH from .env"
  fi
  # Sustituir rutas axis.duckdb por duckclaw.duckdb en claves gateway conocidas.
  for key in DUCKCLAW_GATEWAY_DB_PATH DUCKCLAW_VAULT_DB_PATH DUCKDB_PATH; do
    if grep -q "${key}=.*axis\.duckdb" .env 2>/dev/null; then
      sed -i.bak "s|${key}=\\(.*\\)axis\\.duckdb|${key}=\\1duckclaw.duckdb|g" .env
      rm -f .env.bak
      echo "Updated ${key} axis.duckdb → duckclaw.duckdb in .env"
    fi
  done
fi

echo "Done. Vaults renamed: ${renamed}. Run: uv run duckops stack deploy"
