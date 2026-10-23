"""Identical (tool, args) calls repeated within one turn are cut off by the harness."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.tool_harness import (
    identical_call_block,
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


def test_block_from_the_limit_on(monkeypatch) -> None:
    msgs = [HumanMessage("now")]
    for i in range(2):
        msgs += _round("search", {"q": 1}, i)
    assert identical_call_block(msgs, "search", {"q": 1}) is None  # 3rd run allowed
    msgs += _round("search", {"q": 1}, 2)
    assert json.loads(identical_call_block(msgs, "search", {"q": 1}))["code"] == "harness_identical_call"
    monkeypatch.setenv("DUCKCLAW_MAX_IDENTICAL_TOOL_CALLS", "0")
    assert identical_call_block(msgs, "search", {"q": 1}) is None


def test_block_carries_the_previous_result_even_after_earlier_blocks() -> None:
    args = {"state": "EU defense +8.6%", "questions": [{"type": "score"}]}
    msgs = [HumanMessage("/weekly_digest")]
    for i in range(3):
        msgs += [
            AIMessage(content="", tool_calls=[{"name": "jev_decide", "args": args, "id": f"j{i}"}]),
            ToolMessage(content=json.dumps({"ok": True, "score": 0.7 + i / 100}), tool_call_id=f"j{i}", name="jev_decide"),
        ]
    first = json.loads(identical_call_block(msgs, "jev_decide", args))
    assert first["code"] == "harness_identical_call"
    assert json.loads(first["previous_result"])["score"] == 0.72  # latest real result
    # The block itself becomes a ToolMessage; the next block must still point at the real result.
    msgs += [
        AIMessage(content="", tool_calls=[{"name": "jev_decide", "args": args, "id": "j3"}]),
        ToolMessage(content=json.dumps(first), tool_call_id="j3", name="jev_decide"),
    ]
    second = json.loads(identical_call_block(msgs, "jev_decide", args))
    assert json.loads(second["previous_result"])["score"] == 0.72


def test_varied_args_that_keep_returning_seen_results_are_cut_off() -> None:
    """A Gmail search alternated queries 19 rounds (7 min, 1.16M tokens) getting back only two
    distinct answers; the identical-args guard never fired until the end."""
    from duckclaw.workers.tool_harness import repeated_result_count

    empty, listing = '{"resultSizeEstimate": 0}', '{"threads": [{"id": "1999665e7ea7d014"}]}'
    msgs = [HumanMessage("old"), AIMessage(content="", tool_calls=[{"name": "search_threads", "args": {"q": "x"}, "id": "o1"}]),
            ToolMessage(content=empty, tool_call_id="o1", name="search_threads"), HumanMessage("unread this week")]
    for i, (q, res) in enumerate([("is:unread newer_than:7d", empty), ("is:unread", listing), ("is:unread after:2026/10/15", empty),
                                  ("in:inbox is:unread", listing)]):
        msgs += [AIMessage(content="", tool_calls=[{"name": "search_threads", "args": {"q": q}, "id": f"s{i}"}]),
                 ToolMessage(content=res, tool_call_id=f"s{i}", name="search_threads")]
    assert repeated_result_count(msgs, "search_threads") == 2                 # the previous turn's result does not count
    assert identical_call_block(msgs, "search_threads", {"q": "label:unread"}) is None   # 2 repeats: still allowed
    msgs += [AIMessage(content="", tool_calls=[{"name": "search_threads", "args": {"q": "label:unread"}, "id": "s9"}]),
             ToolMessage(content=empty, tool_call_id="s9", name="search_threads")]
    env = json.loads(identical_call_block(msgs, "search_threads", {"q": "is:unread newer_than:8d"}))
    assert env["code"] == "harness_repeated_result"
    assert "responde al usuario" in env["hint"].lower()
    assert identical_call_block(msgs, "get_thread", {"id": "a"}) is None      # other tools unaffected


def test_distinct_results_of_the_same_tool_never_block() -> None:
    """Reading 20 different emails is progress, not a loop."""
    msgs = [HumanMessage("read them")]
    for i in range(20):
        msgs += [AIMessage(content="", tool_calls=[{"name": "get_thread", "args": {"id": str(i)}, "id": f"g{i}"}]),
                 ToolMessage(content=json.dumps({"id": str(i), "body": f"mail {i}"}), tool_call_id=f"g{i}", name="get_thread")]
    assert identical_call_block(msgs, "get_thread", {"id": "20"}) is None
