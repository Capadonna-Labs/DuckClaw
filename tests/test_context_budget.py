"""Pre-flight token budget for cloud providers: off by default, trims history before the system prompt, flags schema-heavy setups."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from duckclaw.workers.provider_input_budget import (
    apply_context_budget,
    apply_provider_input_budget,
    estimate_tokens_from_messages,
)


def _history(n: int, chars: int = 4000) -> list:
    msgs: list = [SystemMessage(content="sys " * 50)]
    for i in range(n):
        msgs += [HumanMessage(content=f"q{i} " + "x" * chars), AIMessage(content=f"a{i} " + "y" * chars)]
    return msgs


def test_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CONTEXT_BUDGET_TOKENS", raising=False)
    msgs = _history(50)
    assert apply_provider_input_budget(msgs, provider="openrouter", bound_tools_n=300) is msgs


def test_history_is_trimmed_oldest_first_and_system_prompt_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_BUDGET_TOKENS", "20000")
    monkeypatch.setenv("DUCKCLAW_CONTEXT_OUTPUT_RESERVE_TOKENS", "2000")
    msgs = _history(40) + [HumanMessage(content="latest question")]
    out = apply_provider_input_budget(msgs, provider="openrouter", bound_tools_n=0)
    assert estimate_tokens_from_messages(out) <= 18000
    assert isinstance(out[0], SystemMessage) and out[0].content == msgs[0].content
    assert out[-1].content == "latest question"
    assert "q0 " not in str(out[1].content)  # the oldest turns went first


def test_schemas_shrink_the_room_for_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_BUDGET_TOKENS", "40000")
    monkeypatch.setenv("DUCKCLAW_CONTEXT_OUTPUT_RESERVE_TOKENS", "0")
    monkeypatch.setenv("DUCKCLAW_CONTEXT_TOKENS_PER_TOOL", "100")
    msgs = _history(60)
    lean = estimate_tokens_from_messages(apply_context_budget(msgs, bound_tools_n=10))
    heavy = estimate_tokens_from_messages(apply_context_budget(msgs, bound_tools_n=300))
    assert heavy < lean <= 40000 - 10 * 100


def test_a_huge_tool_result_is_cut_to_a_share_of_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_BUDGET_TOKENS", "20000")
    monkeypatch.setenv("DUCKCLAW_CONTEXT_OUTPUT_RESERVE_TOKENS", "0")
    msgs = [SystemMessage(content="s"), HumanMessage(content="go"),
            AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
            ToolMessage(content="z" * 400_000, tool_call_id="1", name="t")]
    out = apply_context_budget(msgs)
    assert len(out[-1].content) <= 20000 // 2 + 100
