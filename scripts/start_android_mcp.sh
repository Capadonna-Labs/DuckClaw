#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
set -a
source "${ROOT}/.env"
set +a
if [[ -z "${ANDROID_MCP_COMMAND:-}" ]]; then
  echo "ANDROID_MCP_COMMAND not set in ${ROOT}/.env" >&2
  exit 1
fi
exec bash -lc "${ANDROID_MCP_COMMAND}"
