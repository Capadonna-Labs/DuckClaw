"""Repeated identical-call blocks end the turn instead of looping until max_tool_rounds."""

from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.tool_harness import (
    harness_abort_reply,
    harness_abort_tool,
    identical_blocks_in_turn,
    identical_call_envelope,
    max_identical_blocks_per_turn,
)

_ARGS = {"chat_id": "research_worker"}


def _call(i: int, content: str) -> list:
    return [
        AIMessage(content="", tool_calls=[{"name": "run_sandbox", "args": _ARGS, "id": f"c{i}"}]),
        ToolMessage(content=content, tool_call_id=f"c{i}", name="run_sandbox"),
    ]


def _turn(blocks: int) -> list:
    msgs: list = [HumanMessage("Genera el perfil de volumen de VG")]
    for i in range(3):
        msgs += _call(i, '{"exit_code": 1, "output": "Error en Sandbox: falta code"}')
    for i in range(blocks):
        msgs += _call(10 + i, identical_call_envelope("run_sandbox", 3 + i))
    return msgs


def test_abort_after_two_identical_blocks(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MAX_IDENTICAL_BLOCKS_PER_TURN", raising=False)
    assert max_identical_blocks_per_turn() == 2
    assert harness_abort_tool(_turn(1)) is None
    assert identical_blocks_in_turn(_turn(2)) == {"run_sandbox": 2}
    assert harness_abort_tool(_turn(2)) == "run_sandbox"
    assert "run_sandbox" in harness_abort_reply("run_sandbox")


def test_blocks_from_previous_turn_do_not_abort(monkeypatch) -> None:
    msgs = _turn(5) + [HumanMessage("otra cosa")]
    assert harness_abort_tool(msgs) is None
    monkeypatch.setenv("DUCKCLAW_MAX_IDENTICAL_BLOCKS_PER_TURN", "0")
    assert harness_abort_tool(_turn(5)) is None


def test_should_continue_ends_on_abort() -> None:
    from duckclaw.workers.factory_graph_nodes_routing import make_should_continue

    sc = make_should_continue(SimpleNamespace(max_tool_rounds=75))
    pending = AIMessage(content="", tool_calls=[{"name": "run_sandbox", "args": _ARGS, "id": "z"}])
    assert sc({"messages": [pending], "_tool_round": 5}) == "tools"
    assert sc({"messages": [pending], "_tool_round": 5, "_harness_abort_tool": "run_sandbox"}) == "end"


def test_set_reply_cap_explains_abort() -> None:
    from duckclaw.workers.factory_set_reply_tool_cap import maybe_reply_for_tool_cap_exhausted

    pending = AIMessage(content="", tool_calls=[{"name": "run_sandbox", "args": _ARGS, "id": "z"}])
    msgs = _turn(2) + [pending]
    state = {"messages": msgs, "_tool_round": 6, "_harness_abort_tool": "run_sandbox"}
    reply, stripped = maybe_reply_for_tool_cap_exhausted(state, SimpleNamespace(max_tool_rounds=75), msgs, "", None)
    assert reply and "run_sandbox" in reply and "bucle" in reply
    assert stripped is not None and not getattr(stripped[-1], "tool_calls", None)
    # no abort and below the cap: untouched
    assert maybe_reply_for_tool_cap_exhausted(
        {"messages": msgs, "_tool_round": 6}, SimpleNamespace(max_tool_rounds=75), msgs, "", None
    ) == (None, None)


def _tools_ctx(tool):
    return SimpleNamespace(
        worker_id="research_worker",
        db=None,
        spec=SimpleNamespace(tool_surface_config={}, allowed_delegates=(), duckdb_extensions=[], read_only=False),
        path="/nonexistent.duckdb",
        shared_resolved=None,
        tools_by_name={"run_sandbox": tool},
        tools_by_name_sandbox_off={},
        use_context_monitor=False,
        sandbox_enabled_for_state=lambda state: True,
        llm=None,
        templates_root=None,
    )


def test_tools_node_counts_blocks_as_failures_and_flags_abort(monkeypatch) -> None:
    """End to end over tools_node: no-code calls → 3 failures, then blocks count, then abort."""
    from duckclaw.graphs.sandbox import sandbox_tool_factory
    from duckclaw.workers import factory_graph_nodes_tools as tn

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", lambda **kw: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("duckclaw.traces.tool_transitions.append_tool_transitions", lambda records: None)
    node = tn.make_tools_node(_tools_ctx(sandbox_tool_factory(db=None, llm=None)))
    state: dict = {"messages": [HumanMessage("Genera el perfil de volumen de VG")], "chat_id": "admin-conv-test"}
    for i in range(5):
        state["messages"] = state["messages"] + [
            AIMessage(content="", tool_calls=[{"name": "run_sandbox", "args": dict(_ARGS), "id": f"t{i}"}])
        ]
        state = node(state)
        if state.get("_harness_abort_tool"):
            break
    assert state.get("_harness_abort_tool") == "run_sandbox"
    assert state["_tool_fail_counts"]["run_sandbox"] == 5  # 3 missing-code + 2 blocked repeats
    first = json.loads(state["messages"][2].content)
    assert first.get("error_code") == "missing_code"


def test_mini_graph_no_code_loop_ends_in_few_rounds(monkeypatch) -> None:
    """Replays 2026-10-24: a model that always re-sends run_sandbox without code. With the real
    tools_node + should_continue + set_reply cap helper the turn ends after 5 rounds, not 75."""
    from langgraph.graph import END, StateGraph

    from duckclaw.graphs.sandbox import sandbox_tool_factory
    from duckclaw.workers import factory_graph_nodes_tools as tn
    from duckclaw.workers.factory_graph_nodes_routing import make_should_continue
    from duckclaw.workers.factory_set_reply_tool_cap import maybe_reply_for_tool_cap_exhausted

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", lambda **kw: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("duckclaw.traces.tool_transitions.append_tool_transitions", lambda records: None)
    ctx = SimpleNamespace(max_tool_rounds=75)
    llm_calls = {"n": 0}

    def agent(state: dict) -> dict:
        llm_calls["n"] += 1
        call = AIMessage(content="", tool_calls=[{"name": "run_sandbox", "args": dict(_ARGS), "id": f"a{llm_calls['n']}"}])
        return {**state, "messages": state["messages"] + [call]}

    def set_reply(state: dict) -> dict:
        reply, msgs = maybe_reply_for_tool_cap_exhausted(state, ctx, list(state["messages"]), "", None)
        return {**state, "messages": msgs or state["messages"], "reply": reply}

    g = StateGraph(dict)
    g.add_node("agent", agent)
    g.add_node("tools", tn.make_tools_node(_tools_ctx(sandbox_tool_factory(db=None, llm=None))))
    g.add_node("set_reply", set_reply)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", make_should_continue(ctx), {"tools": "tools", "end": "set_reply"})
    g.add_edge("tools", "agent")
    g.add_edge("set_reply", END)
    out = g.compile().invoke(
        {"messages": [HumanMessage("Genera el perfil de volumen de VG")], "chat_id": "admin-conv-test"},
        {"recursion_limit": 40},
    )
    assert out["_tool_round"] == 5  # 3 missing-code errors + 2 blocked repeats
    assert llm_calls["n"] == 6
    assert out["reply"] and "bucle" in out["reply"]
    assert not getattr(out["messages"][-1], "tool_calls", None)
