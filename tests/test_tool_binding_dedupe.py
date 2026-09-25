"""Dedupe tools by name — Gemini rejects duplicate function declarations."""

from __future__ import annotations

from types import SimpleNamespace

from duckclaw.workers.tool_binding import dedupe_tools_by_name


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_dedupe_tools_by_name_keeps_first() -> None:
    a = _tool("mcp__github__get_commit")
    b = _tool("mcp__github__get_commit")
    c = _tool("read_sql")
    out = dedupe_tools_by_name([a, b, c])
    assert [t.name for t in out] == ["mcp__github__get_commit", "read_sql"]
    assert out[0] is a


def test_dedupe_tools_by_name_empty_and_blank() -> None:
    assert dedupe_tools_by_name([]) == []
    blank = _tool("")
    assert dedupe_tools_by_name([blank, blank]) == [blank, blank]
