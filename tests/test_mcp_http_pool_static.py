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


def test_pool_keeps_one_session_per_endpoint_under_concurrency(monkeypatch) -> None:
    """Two connectors listed concurrently must not close each other's session."""
    import asyncio
    import sys
    import threading
    import types

    from duckclaw.forge.skills import mcp_http_pool as pool_mod

    opened: list[str] = []
    closed: list[str] = []

    class FakeTransport:
        def __init__(self, url, http_client=None):
            self.url = url

        async def __aenter__(self):
            opened.append(self.url)
            return (self.url, None, None)

        async def __aexit__(self, *exc):
            closed.append(self.url)

    class FakeSession:
        def __init__(self, read_stream, _write):
            self.url = read_stream
            self.alive = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.alive = False

        async def initialize(self):
            await asyncio.sleep(0.01)

        async def list_tools(self):
            await asyncio.sleep(0.05)  # other connectors connect meanwhile
            if not self.alive:
                raise RuntimeError("closed")
            return types.SimpleNamespace(tools=[self.url])

    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", types.SimpleNamespace(streamable_http_client=FakeTransport))
    monkeypatch.setitem(sys.modules, "mcp", types.SimpleNamespace(ClientSession=FakeSession))
    pool = pool_mod._McpHttpPool()
    results: dict[str, list] = {}

    def worker(url: str) -> None:
        for _ in range(3):
            results[url] = pool.list_tools(url, headers={"Authorization": url})

    threads = [threading.Thread(target=worker, args=(u,)) for u in ("https://a/mcp", "https://b/mcp", "https://c/mcp")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {u: [u] for u in ("https://a/mcp", "https://b/mcp", "https://c/mcp")}
    assert sorted(opened) == ["https://a/mcp", "https://b/mcp", "https://c/mcp"]  # reused, not reopened
    assert closed == []
