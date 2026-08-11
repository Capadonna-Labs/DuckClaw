#!/usr/bin/env bash
set -euo pipefail
ROOT="${DUCKCLAW_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${ROOT}"
set -a
# shellcheck disable=SC1091
source .env 2>/dev/null || true
set +a

uv run python -c "
from duckclaw.mcp_android_vision import is_android_screenshot_tool
from duckclaw.forge.skills.mcp_http_pool import mcp_http_pool_enabled
from duckclaw.framework_policy_pack import get_framework_policy_content
d = get_framework_policy_content('directive', 'android_mcp') or ''
print('vision_module', is_android_screenshot_tool('mcp__android__get_screenshot'))
print('http_pool', mcp_http_pool_enabled())
print('android_directive_len', len(d))
"

uv run python scripts/verify_android_mcp.py
echo smoke_ok
