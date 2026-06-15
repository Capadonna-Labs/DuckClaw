from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from duckclaw.workers.provider_input_budget import (
    apply_provider_input_budget,
    estimate_tokens_from_messages,
    normalized_context_pruning,
    split_for_pruning,
)


def test_normalized_context_pruning_clamps_config_values() -> None:
    spec = SimpleNamespace(
        context_pruning_config={
            "enabled": True,
            "max_messages": 1,
            "max_estimated_tokens": 10,
            "keep_last_messages": 0,
            "tool_content_max_chars": 10,
            "sandbox_heartbeat": False,
        }
    )

    out = normalized_context_pruning(spec)

    assert out == {
        "enabled": True,
        "max_messages": 2,
        "max_estimated_tokens": 500,
        "keep_last_messages": 1,
        "tool_content_max_chars": 500,
        "sandbox_heartbeat": False,
    }


def test_provider_input_budget_uses_tool_truncation_and_preserves_recent_context(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DUCKCLAW_GROQ_MAX_INPUT_TOKENS", "1500")
    monkeypatch.setenv("DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS", "400")
    messages = [
        SystemMessage(content="system " + "s" * 1000),
        HumanMessage(content="old " + "x" * 6000),
        ToolMessage(content="tool " + "t" * 2000, tool_call_id="tool-1", name="read_sql"),
        HumanMessage(content="recent question"),
    ]

    out = apply_provider_input_budget(messages, provider="groq")

    assert isinstance(out[0], SystemMessage)
    assert out[-1].content == "recent question"
    assert all(getattr(message, "content", "") != messages[1].content for message in out)
    assert estimate_tokens_from_messages(out) <= 1500
    tool_messages = [message for message in out if isinstance(message, ToolMessage)]
    assert tool_messages
    assert str(tool_messages[0].content).endswith("\n…[truncado por tamaño]")


def test_split_for_pruning_keeps_ai_tool_call_with_following_tool_result() -> None:
    ai_with_tool = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_sql", "args": {}}],
    )
    tool_result = ToolMessage(content="result", tool_call_id="call-1", name="read_sql")
    non_system = [
        HumanMessage(content="old"),
        ai_with_tool,
        tool_result,
    ]

    head, tail = split_for_pruning(non_system, keep_last=1)

    assert head == [non_system[0]]
    assert tail == [ai_with_tool, tool_result]
