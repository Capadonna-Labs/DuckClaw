#!/bin/sh
set -eu
export DUCKCLAW_GATEWAY_DB_PATH="${DUCKCLAW_GATEWAY_DB_PATH:-/data/duckclaw.duckdb}"
export DUCKCLAW_REPO_ROOT="${DUCKCLAW_REPO_ROOT:-/app}"
mkdir -p "$(dirname "$DUCKCLAW_GATEWAY_DB_PATH")"
if [ "${DUCKCLAW_SKIP_MIGRATE:-0}" != "1" ]; then
  echo "[entrypoint] duckclaw-migrate ($DUCKCLAW_GATEWAY_DB_PATH)"
  duckclaw-migrate || {
    echo "[entrypoint] migrate failed" >&2
    exit 1
  }
else
  echo "[entrypoint] skip migrate (DUCKCLAW_SKIP_MIGRATE=1)"
fi
echo "[entrypoint] starting: $*"
exec "$@"
