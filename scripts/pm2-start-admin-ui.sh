#!/usr/bin/env bash
# PM2 entrypoint for duckclaw-admin-ui (Next.js standalone).
# Spec: docs/deploy/GITHUB_ACTIONS_CD.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN="${ROOT}/apps/duckclaw-admin"
STANDALONE="${ADMIN}/.next/standalone"
SERVER="${STANDALONE}/server.js"

if [[ ! -f "${SERVER}" ]]; then
  echo "Missing ${SERVER} — deploy standalone build first" >&2
  exit 1
fi

export PORT="${PORT:-3000}"
# Next standalone binds to $HOSTNAME. The shell/OS hostname (e.g. ubuntu-…)
# resolves to 127.0.1.1 and breaks nginx/Tailscale — always force all interfaces.
export HOSTNAME="${DUCKCLAW_ADMIN_BIND_HOST:-0.0.0.0}"
export NODE_ENV=production

# Load app env BEFORE defaulting REPO_ROOT so .env.local can point
# DUCKCLAW_EXTENSION_ROOT / DUCKCLAW_REPO_ROOT at the product vault tree
# (must match the gateway writer). Otherwise /api/admin/artifacts → 404 and
# chat/preview show broken <img> even when PNGs exist on disk.
# Do NOT source monorepo ROOT/.env here — it can pull HOSTNAME/MCP ports that
# break the Next bind.
set -a
# shellcheck disable=SC1091
[[ -f "${ADMIN}/.env.local" ]] && . "${ADMIN}/.env.local"
# shellcheck disable=SC1091
[[ -f "${STANDALONE}/.env.local" ]] && . "${STANDALONE}/.env.local"
# shellcheck disable=SC1091
[[ -f "${STANDALONE}/.env" ]] && . "${STANDALONE}/.env"
set +a

export DUCKCLAW_REPO_ROOT="${DUCKCLAW_REPO_ROOT:-${ROOT}}"
export HOSTNAME="${DUCKCLAW_ADMIN_BIND_HOST:-0.0.0.0}"

cd "${STANDALONE}"
exec node server.js
