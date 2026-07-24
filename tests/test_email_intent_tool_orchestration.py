"""Email intent detection and Gmail MCP tool resolution."""

from __future__ import annotations

from duckclaw.workers.tool_orchestration import (
    find_gmail_mcp_search_tool,
    incoming_has_email_intent,
)


def test_incoming_has_email_intent_spanish() -> None:
    assert incoming_has_email_intent("busca el correo y saca insights")
    assert incoming_has_email_intent("revisa mi bandeja de entrada")
    assert not incoming_has_email_intent("analiza esta imagen")


def test_find_gmail_mcp_search_tool_prefers_gmail_named() -> None:
    tools = {
        "mcp__notion__search_threads": object(),
        "mcp__google_gmail__search_threads": object(),
    }
    assert find_gmail_mcp_search_tool(tools) == "mcp__google_gmail__search_threads"


def test_find_gmail_mcp_search_tool_single_candidate() -> None:
    tools = {"mcp__abc123__search_threads": object()}
    assert find_gmail_mcp_search_tool(tools) == "mcp__abc123__search_threads"
