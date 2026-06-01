#!/usr/bin/env bash
# Canonical MLX text launcher. Delegates to the legacy path until PM2/docs move.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY="${SCRIPT_DIR}/../start_mlx.sh"
exec bash "${LEGACY}" "$@"
