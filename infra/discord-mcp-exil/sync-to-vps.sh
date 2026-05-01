#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-capadonna@100.97.151.69}"
REMOTE_DIR="${REMOTE_DIR:-/home/capadonna/services/discord-mcp-exil}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh "$TARGET" "mkdir -p '$REMOTE_DIR'"

rsync -avz \
  "${SCRIPT_DIR}/Dockerfile" \
  "${SCRIPT_DIR}/docker-compose.yml" \
  "${SCRIPT_DIR}/env.template" \
  "$TARGET:${REMOTE_DIR}/"

ssh "$TARGET" bash -s <<REMOTE
set -euo pipefail
cd '${REMOTE_DIR}'
if [ ! -d discord-src/.git ]; then
  rm -rf discord-src
  git clone --depth 1 https://github.com/ExilProductions/discord-mcp.git discord-src
fi
if [ ! -f .env ]; then
  cp env.template .env
  echo '[discord-mcp-exil] creado .env desde env.template'
fi
docker compose build
docker compose up -d
docker compose ps
REMOTE
