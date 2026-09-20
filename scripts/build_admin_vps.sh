#!/usr/bin/env bash
# Low-memory Next.js build for 2GB VPS. Skips TS/eslint via DUCKCLAW_ADMIN_RELAX_BUILD=1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN="${ROOT}/apps/duckclaw-admin"

echo "── Stopping heavy PM2 apps to free RAM ──"
pm2 stop DuckClaw-Gateway DuckClaw-DB-Writer 2>/dev/null || true
sync
sleep 2

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
pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer --update-env 2>/dev/null || true
pm2 save 2>/dev/null || true
