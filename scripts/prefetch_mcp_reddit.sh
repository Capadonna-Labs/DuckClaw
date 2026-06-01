#!/usr/bin/env bash
# Compatibilidad: la implementación vive en DuckOps.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
exec uv run duckops mcp prefetch reddit "$@"
