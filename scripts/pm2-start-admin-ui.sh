#!/usr/bin/env bash
# Start Next standalone admin UI with only the env vars the BFF needs.
# Avoid `source .env` (can pull MCP/MLX side-effects into the Node process).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAND="$ROOT/apps/duckclaw-admin/.next/standalone"
SERVER="$STAND/server.js"
if [[ ! -f "$SERVER" ]]; then
  echo "FATAL: missing standalone server at $SERVER" >&2
  exit 1
fi
cd "$STAND"

read_env_key() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "$file" | head -1 || true)"
  [[ -n "$line" ]] || return 0
  printf '%s' "${line#*=}" | sed -e 's/\r$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

export PORT="${PORT:-3000}"
export HOSTNAME="${HOSTNAME:-0.0.0.0}"
export NODE_ENV=production
export DUCKCLAW_GATEWAY_URL="${DUCKCLAW_GATEWAY_URL:-$(read_env_key "$ROOT/.env" DUCKCLAW_GATEWAY_URL)}"
export DUCKCLAW_GATEWAY_URL="${DUCKCLAW_GATEWAY_URL:-http://127.0.0.1:8000}"
export GATEWAY_INTERNAL_URL="${GATEWAY_INTERNAL_URL:-$DUCKCLAW_GATEWAY_URL}"
export DUCKCLAW_ADMIN_API_KEY="${DUCKCLAW_ADMIN_API_KEY:-$(read_env_key "$STAND/.env" DUCKCLAW_ADMIN_API_KEY)}"
export DUCKCLAW_ADMIN_API_KEY="${DUCKCLAW_ADMIN_API_KEY:-$(read_env_key "$ROOT/apps/duckclaw-admin/.env.local" DUCKCLAW_ADMIN_API_KEY)}"
export DUCKCLAW_ADMIN_API_KEY="${DUCKCLAW_ADMIN_API_KEY:-$(read_env_key "$ROOT/.env" DUCKCLAW_ADMIN_API_KEY)}"

if [[ -z "${DUCKCLAW_ADMIN_API_KEY}" ]]; then
  echo "FATAL: DUCKCLAW_ADMIN_API_KEY missing (root .env / admin .env.local)" >&2
  exit 1
fi

exec node "$SERVER"
