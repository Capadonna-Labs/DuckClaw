#!/usr/bin/env bash
# Empaqueta Next.js standalone (+ static + public) para desplegar en el VPS sin build allí.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADMIN="${ROOT}/apps/duckclaw-admin"
OUT="${1:-${ROOT}/dist/admin-standalone.tgz}"

cd "${ADMIN}"
test -f .next/BUILD_ID || { echo "Falta .next/BUILD_ID — corre pnpm build antes"; exit 1; }
test -f .next/standalone/server.js || { echo "Falta standalone/server.js"; exit 1; }

mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static
cp -a .next/static .next/standalone/.next/static
if [[ -d public ]]; then
  rm -rf .next/standalone/public
  cp -a public .next/standalone/public
fi

mkdir -p "$(dirname "${OUT}")"
tar -C .next -czf "${OUT}" standalone BUILD_ID static
echo "Packed ${OUT} (BUILD_ID=$(cat .next/BUILD_ID))"
