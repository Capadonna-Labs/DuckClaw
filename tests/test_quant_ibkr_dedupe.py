"""Tests for IBKR portfolio dedupe helpers in worker factory."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage


def test_quant_strip_duplicate_ibkr_portfolio_when_already_in_turn() -> None:
    from duckclaw.workers.factory import _quant_strip_duplicate_ibkr_portfolio_tool_calls

    messages = [
        HumanMessage(content="resumen portfolio"),
        ToolMessage(content='{"ok": true}', tool_call_id="t1", name="get_ibkr_portfolio"),
    ]
    tool_calls = [{"name": "get_ibkr_portfolio", "args": {}, "id": "t2", "type": "tool_call"}]
    out = _quant_strip_duplicate_ibkr_portfolio_tool_calls(
        messages, tool_calls, last_human_idx=0
    )
    assert out == []


def test_quant_strip_keeps_first_portfolio_in_batch_only() -> None:
    from duckclaw.workers.factory import _quant_strip_duplicate_ibkr_portfolio_tool_calls

    messages = [HumanMessage(content="hola")]
    tool_calls = [
        {"name": "get_ibkr_portfolio", "args": {}, "id": "a", "type": "tool_call"},
        {"name": "get_ibkr_portfolio", "args": {}, "id": "b", "type": "tool_call"},
        {"name": "read_sql", "args": {"query": "select 1"}, "id": "c", "type": "tool_call"},
    ]
    out = _quant_strip_duplicate_ibkr_portfolio_tool_calls(
        messages, tool_calls, last_human_idx=0
    )
    names = [tc["name"] for tc in out]
    assert names == ["get_ibkr_portfolio", "read_sql"]
