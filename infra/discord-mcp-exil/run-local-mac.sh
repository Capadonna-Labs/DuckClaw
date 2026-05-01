#!/usr/bin/env bash
# Arranca Exil discord_mcp sobre 127.0.0.1:8010 para no chocar con DuckClaw :8000 (+ Funnel loopback).
# Uso: ./infra/discord-mcp-exil/run-local-mac.sh
#      DISCORD_MCP_PYTHON=/opt/homebrew/bin/python3 ./infra/discord-mcp-exil/run-local-mac.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8010}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
PY="${DISCORD_MCP_PYTHON:-python3}"
exec "$PY" -m discord_mcp.main
