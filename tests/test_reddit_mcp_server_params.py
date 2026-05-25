"""Resolución de comando stdio para mcp-reddit (prefetch vs npx)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from duckclaw.forge.skills import reddit_bridge as rb


def test_reddit_mcp_server_params_uses_prefetch_node_when_cached(tmp_path: Path) -> None:
    pkg = "mcp-reddit"
    server = tmp_path / "node_modules" / pkg / "dist" / "server.js"
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_text("// stub", encoding="utf-8")

    with patch.dict(os.environ, {"DUCKCLAW_REDDIT_MCP_CACHE_DIR": str(tmp_path)}, clear=False):
        params = rb.reddit_mcp_server_params(pkg)
    assert params.command.endswith("node") or "node" in params.command
    assert params.args == [str(server)]


def test_reddit_mcp_server_params_custom_command_override() -> None:
    with patch.dict(
        os.environ,
        {
            "DUCKCLAW_REDDIT_MCP_COMMAND": "/usr/bin/node",
            "DUCKCLAW_REDDIT_MCP_ARGS": "/opt/mcp-reddit.js --foo",
        },
        clear=False,
    ):
        params = rb.reddit_mcp_server_params()
    assert params.command == "/usr/bin/node"
    assert params.args == ["/opt/mcp-reddit.js", "--foo"]


def test_reddit_mcp_using_prefetch_false_without_cache(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with patch.dict(os.environ, {"DUCKCLAW_REDDIT_MCP_CACHE_DIR": str(empty)}, clear=False):
        assert rb.reddit_mcp_using_prefetch() is False
