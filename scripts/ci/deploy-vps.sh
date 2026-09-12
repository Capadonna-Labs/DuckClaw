#!/usr/bin/env bash
# Deploy desde CI: git pull en VPS + admin standalone prebuilt + restart PM2.
# Secrets: VPS_HOST, VPS_SSH_KEY. Opcionales: VPS_USER (root), VPS_PATH (/root/duckclaw).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${VPS_HOST:-}"
USER_NAME="${VPS_USER:-root}"
REMOTE_PATH="${VPS_PATH:-/root/duckclaw}"
KEY_FILE="${VPS_SSH_KEY_FILE:-}"
TGZ="${ADMIN_STANDALONE_TGZ:-${ROOT}/dist/admin-standalone.tgz}"

if [[ -z "${HOST}" ]]; then
  echo "VPS_HOST vacío — configure el secret VPS_HOST"
  exit 1
fi
if [[ -z "${KEY_FILE}" || ! -f "${KEY_FILE}" ]]; then
  echo "VPS_SSH_KEY_FILE inválido"
  exit 1
fi
if [[ ! -f "${TGZ}" ]]; then
  echo "Falta artefacto ${TGZ}"
  exit 1
fi

SSH=(ssh -i "${KEY_FILE}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
SCP=(scp -i "${KEY_FILE}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
REMOTE="${USER_NAME}@${HOST}"

echo "── Upload admin standalone → ${REMOTE}:${REMOTE_PATH} ──"
"${SCP[@]}" "${TGZ}" "${REMOTE}:/tmp/duckclaw-admin-standalone.tgz"

echo "── Remote pull + unpack + PM2 restart ──"
"${SSH[@]}" "${REMOTE}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_PATH}"
git fetch origin main
git checkout main
git pull --ff-only origin main

# Python deps (rápido si el lock no cambió)
if command -v uv >/dev/null 2>&1; then
  uv sync --frozen 2>/dev/null || uv sync || true
fi

ADMIN_NEXT="${REMOTE_PATH}/apps/duckclaw-admin/.next"
mkdir -p "\${ADMIN_NEXT}"
# Preserve any local env files under standalone
ENV_BAK=\$(mktemp -d)
cp -a "\${ADMIN_NEXT}/standalone/.env" "\${ENV_BAK}/" 2>/dev/null || true
cp -a "\${ADMIN_NEXT}/standalone/.env.local" "\${ENV_BAK}/" 2>/dev/null || true
cp -a "\${ADMIN_NEXT}/standalone/.env.production" "\${ENV_BAK}/" 2>/dev/null || true

rm -rf "\${ADMIN_NEXT}/standalone" "\${ADMIN_NEXT}/static"
tar -C "\${ADMIN_NEXT}" -xzf /tmp/duckclaw-admin-standalone.tgz
cp -a "\${ENV_BAK}/." "\${ADMIN_NEXT}/standalone/" 2>/dev/null || true
rm -rf "\${ENV_BAK}" /tmp/duckclaw-admin-standalone.tgz

test -f "\${ADMIN_NEXT}/standalone/server.js"
echo "BUILD_ID=\$(cat "\${ADMIN_NEXT}/BUILD_ID")"

pm2 restart duckclaw-admin-ui --update-env || pm2 start scripts/pm2-start-admin-ui.sh --name duckclaw-admin-ui
pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer DuckClaw-Heartbeat --update-env || true
pm2 save || true
pm2 list | grep -E "duckclaw-admin-ui|DuckClaw-" || pm2 list
curl -sS -o /dev/null -w "admin_http=%{http_code}\\n" http://127.0.0.1:3000/login || true
curl -sS -o /dev/null -w "gateway_http=%{http_code}\\n" http://127.0.0.1:8000/health || true
EOF

echo "── Deploy OK ──"
