#!/usr/bin/env bash
# Canonical MLX vision launcher. Delegates to the legacy path until PM2/docs move.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY="${SCRIPT_DIR}/../start_mlx_vision.sh"
exec bash "${LEGACY}" "$@"
