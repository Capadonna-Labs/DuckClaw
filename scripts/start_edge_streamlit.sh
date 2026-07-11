#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
uv sync --project integrations/edge-devices
exec uv run --project integrations/edge-devices streamlit run \
  integrations/edge-devices/src/duckclaw_edge_devices/app.py \
  --server.headless true \
  --server.port "${DUCKCLAW_EDGE_STREAMLIT_PORT:-8501}"
