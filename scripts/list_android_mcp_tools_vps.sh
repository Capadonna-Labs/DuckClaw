#!/usr/bin/env bash
set -euo pipefail
ROOT="${DUCKCLAW_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${ROOT}"
set -a
# shellcheck disable=SC1091
source .env
set +a
uv run python <<'PY'
import json, os, urllib.request
base = (os.environ.get("DUCKCLAW_GATEWAY_URL") or "http://127.0.0.1:8000").rstrip("/")
key = os.environ["DUCKCLAW_ADMIN_API_KEY"]
h = {"X-Admin-Key": key, "Content-Type": "application/json"}
req = urllib.request.Request(
    f"{base}/api/v1/admin/mcp/connectors/mcp_android/test",
    data=b"{}",
    headers=h,
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    t = json.load(resp)
for x in t.get("tools") or []:
    print(f"{x.get('name')}: {(x.get('description') or '')[:160]}")
PY
