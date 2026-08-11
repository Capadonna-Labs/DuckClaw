"""Tests harness_max_chars_for_tool android ui_dump."""
from __future__ import annotations

from duckclaw.workers.tool_harness import harness_max_chars_for_tool


def test_ui_dump_gets_higher_harness_budget() -> None:
    assert harness_max_chars_for_tool("mcp__android__get_ui_dump", 12_000) == 48_000


def test_other_tools_keep_default() -> None:
    assert harness_max_chars_for_tool("mcp__android__swipe_screen", 12_000) == 12_000
