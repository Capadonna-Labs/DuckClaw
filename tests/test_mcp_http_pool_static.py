"""Static checks for MCP HTTP session pool."""
from __future__ import annotations

from pathlib import Path


def test_mcp_http_pool_module_exists() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "packages/agents/src/duckclaw/forge/skills/mcp_http_pool.py"
    text = path.read_text(encoding="utf-8")
    assert "mcp_http_call_tool_pooled" in text
    assert "DUCKCLAW_MCP_HTTP_POOL" in text
    assert "_McpHttpPool" in text
