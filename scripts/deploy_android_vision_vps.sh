#!/usr/bin/env bash
# ponytail: one-shot deploy android vision + MCP HTTP pool
set -euo pipefail
ROOT="${DUCKCLAW_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${ROOT}"
set -a
# shellcheck disable=SC1091
source .env 2>/dev/null || true
set +a

uv run python <<'PY'
from duckclaw.framework_policy_pack import apply_framework_policy_pack
import duckdb
from duckclaw.gateway_db import get_gateway_db_path

p = get_gateway_db_path()
con = duckdb.connect(p)
try:
    n = apply_framework_policy_pack(con)
    print("policy_pack_applied", n)
finally:
    con.close()
PY

pm2 restart DuckClaw-Gateway
sleep 4
pm2 status DuckClaw-Gateway | head -8

if [ -f scripts/verify_android_mcp.py ]; then
  uv run python scripts/verify_android_mcp.py && echo "verify_android_mcp: OK" || echo "verify_android_mcp: WARN"
fi

echo "deploy_android_vision: done"
