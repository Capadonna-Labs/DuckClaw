"""Tests loader catálogo MCP oficial."""

from __future__ import annotations

import sys
from pathlib import Path

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.mcp_official_catalog import load_official_mcp_reference


def test_load_official_mcp_reference_has_seven_servers():
    repo = Path(__file__).resolve().parents[1]
    data = load_official_mcp_reference(repo)
    assert data["source_label"] == "modelcontextprotocol/servers"
    servers = data["servers"]
    assert len(servers) == 7
    ids = {s["id"] for s in servers}
    assert "memory" in ids
    assert "git" in ids
    git = next(s for s in servers if s["id"] == "git")
    assert git["runtime"] == "uvx"
    assert "mcp-server-git" in git["install"]
