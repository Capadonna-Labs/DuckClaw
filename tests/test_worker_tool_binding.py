from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, ToolMessage


@dataclass(frozen=True)
class ToolStub:
    name: str


def test_filter_tools_for_sandbox_removes_sandbox_tools_only_when_disabled() -> None:
    from duckclaw.workers.tool_binding import filter_tools_for_sandbox

    tools = [
        ToolStub("read_sql"),
        ToolStub("run_sandbox"),
        ToolStub("run_browser_sandbox"),
        ToolStub("get_browser_session_url"),
        ToolStub("generate_visual_asset"),
    ]

    assert filter_tools_for_sandbox(tools, enabled=True) == tools
    assert [tool.name for tool in filter_tools_for_sandbox(tools, enabled=False)] == [
        "read_sql",
        "generate_visual_asset",
    ]


def test_groq_tools_without_reddit_for_bind_keeps_non_reddit_tools() -> None:
    from duckclaw.workers.tool_binding import groq_tools_without_reddit_for_bind

    tools = [
        ToolStub("read_sql"),
        ToolStub("reddit_get_post"),
        ToolStub("reddit_search_reddit"),
        ToolStub("tavily_search"),
    ]

    assert [tool.name for tool in groq_tools_without_reddit_for_bind(tools)] == [
        "read_sql",
        "tavily_search",
    ]


def test_tool_choice_function_builds_openai_compatible_choice() -> None:
    from duckclaw.workers.tool_binding import tool_choice_function

    assert tool_choice_function("read_sql") == {
        "type": "function",
        "function": {"name": "read_sql"},
    }


def test_tool_called_since_only_counts_after_last_human_message() -> None:
    from duckclaw.workers.tool_binding import tool_called_since

    messages = [
        ToolMessage(content="old", name="read_sql", tool_call_id="call-1"),
        HumanMessage(content="ahora"),
        ToolMessage(content="new", name="read_sql", tool_call_id="call-2"),
    ]

    assert tool_called_since(messages, 1, "read_sql")
    assert not tool_called_since(messages, 1, "inspect_schema")
    assert not tool_called_since(messages, 2, "read_sql")
