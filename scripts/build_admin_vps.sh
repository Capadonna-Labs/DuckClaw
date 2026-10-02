#!/usr/bin/env bash
# Next.js admin build on the VPS. Skips TS/eslint via DUCKCLAW_ADMIN_RELAX_BUILD=1.
# Stopping the Gateway kills in-flight chat turns, so it only happens when RAM is
# short (DUCKCLAW_ADMIN_BUILD_MIN_FREE_MB, default 2000 MB available).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN="${ROOT}/apps/duckclaw-admin"

AVAIL_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
STOPPED_HEAVY=0
if [ "${AVAIL_MB}" -lt "${DUCKCLAW_ADMIN_BUILD_MIN_FREE_MB:-2000}" ]; then
  echo "── Only ${AVAIL_MB} MB free: stopping heavy PM2 apps (in-flight turns will be cut) ──"
  pm2 stop DuckClaw-Gateway DuckClaw-DB-Writer 2>/dev/null || true
  STOPPED_HEAVY=1
  sync
  sleep 2
else
  echo "── ${AVAIL_MB} MB free: building with Gateway running ──"
fi

echo "── Admin build (relaxed, capped heap) ──"
cd "${ADMIN}"
export DUCKCLAW_ADMIN_RELAX_BUILD=1
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=1536}"
export NEXT_TELEMETRY_DISABLED=1
pnpm run build

test -f .next/BUILD_ID || { echo "BUILD_ID missing — build failed"; exit 1; }
echo "── Build OK: $(cat .next/BUILD_ID) ──"

# ponytail: next build traces standalone/server.js but does NOT copy .next/static
# into it (known Next.js standalone quirk) — without this, every _next/static/*
# chunk 404s on first request after a rebuild.
echo "── Copying .next/static into standalone ──"
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static

echo "── Restoring tracked public assets ──"
git -C "${ROOT}" restore -- apps/duckclaw-admin/public 2>/dev/null || true

echo "── Restart PM2 ──"
cd "${ROOT}"
pm2 restart duckclaw-admin-ui --update-env 2>/dev/null || pm2 start config/ecosystem.spawn.config.cjs --only duckclaw-admin-ui
if [ "${STOPPED_HEAVY}" = 1 ]; then
  pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer --update-env 2>/dev/null || true
fi
pm2 save 2>/dev/null || true
