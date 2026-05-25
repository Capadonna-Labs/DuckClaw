#!/usr/bin/env bash
# Precarga mcp-reddit en .mcp-cache/reddit para evitar npx (2–5 min) en cada cold start del gateway.
# Spec: specs/features/quant/QUANT_REDDIT_MCP_SENTIMENT.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${DUCKCLAW_REDDIT_MCP_CACHE_DIR:-$ROOT/.mcp-cache/reddit}"
PKG="${DUCKCLAW_REDDIT_MCP_NPM_PACKAGE:-mcp-reddit}"
VER="${DUCKCLAW_REDDIT_MCP_NPM_VERSION:-1.1.8}"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm no está en PATH. Instala Node.js 20+." >&2
  exit 1
fi

mkdir -p "$CACHE"
cd "$CACHE"

if [[ ! -f package.json ]]; then
  npm init -y >/dev/null 2>&1
fi

echo "Instalando ${PKG}@${VER} en ${CACHE} ..."
npm install "${PKG}@${VER}" --no-fund --no-audit 2>&1 | tail -5

SERVER="node_modules/${PKG}/dist/server.js"
if [[ ! -f "$SERVER" ]]; then
  echo "Error: no se encontró ${SERVER} tras npm install." >&2
  exit 1
fi

echo "OK: $(realpath "$SERVER" 2>/dev/null || echo "$CACHE/$SERVER")"
echo "Reinicia DuckClaw-Gateway: pm2 restart DuckClaw-Gateway"
