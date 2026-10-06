"""Identical (tool, args) calls repeated within one turn are cut off by the harness."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.tool_harness import (
    identical_call_envelope,
    identical_prior_calls,
    max_identical_tool_calls,
)


def _round(name: str, args: dict, i: int) -> list:
    return [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}]),
        ToolMessage(content="{}", tool_call_id=f"c{i}", name=name),
    ]


def test_counts_only_identical_calls_in_the_current_turn() -> None:
    q = {"query": "from:broker", "max": 10}
    msgs = [HumanMessage("old turn"), *_round("search", q, 0), HumanMessage("now")]
    for i in range(1, 4):
        msgs += _round("search", q, i)
    msgs += _round("search", {"query": "other"}, 9)
    # key order in args does not matter; the earlier turn's call is not counted
    assert identical_prior_calls(msgs, "search", {"max": 10, "query": "from:broker"}) == 3
    assert identical_prior_calls(msgs, "search", {"query": "other"}) == 1
    assert identical_prior_calls(msgs, "read_sql", q) == 0


def test_limit_env_and_envelope(monkeypatch) -> None:
    assert max_identical_tool_calls() == 3
    monkeypatch.setenv("DUCKCLAW_MAX_IDENTICAL_TOOL_CALLS", "0")
    assert max_identical_tool_calls() == 0
    env = json.loads(identical_call_envelope("search", 3))
    assert env["ok"] is False and env["code"] == "harness_identical_call"
