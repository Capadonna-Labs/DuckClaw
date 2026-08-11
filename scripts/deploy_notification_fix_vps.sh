#!/usr/bin/env bash
# Deploy notification-dismiss prompt + ui_dump harness fix
set -euo pipefail
ROOT="${DUCKCLAW_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${ROOT}"
set -a
# shellcheck disable=SC1091
source .env
set +a

curl -sf -X POST "${DUCKCLAW_GATEWAY_URL:-http://127.0.0.1:8000}/api/v1/admin/gateway/release-worker-cache" \
  -H "X-Admin-Key: ${DUCKCLAW_ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{}' >/dev/null && echo "worker cache released"

pm2 restart DuckClaw-Gateway
sleep 4
pm2 status DuckClaw-Gateway | head -6
echo deploy_notification_fix: done
