"""Guardrail: stop repeated read_sql thrash on normal Quant turns."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


def _msgs_with_sql(n: int) -> list:
    out: list = [HumanMessage(content="profundiza NVDA")]
    for i in range(n):
        out.append(AIMessage(content="", tool_calls=[{"name": "read_sql", "args": {}, "id": f"c{i}"}]))
        out.append(ToolMessage(content=f"rows {i}", name="read_sql", tool_call_id=f"c{i}"))
    return out


def test_count_sql_tools_counts_duplicates_not_set() -> None:
    from duckclaw.workers.sql_thrash import count_sql_tools_since_last_human

    assert count_sql_tools_since_last_human(_msgs_with_sql(3)) == 3
    assert count_sql_tools_since_last_human(_msgs_with_sql(1)) == 1


def test_is_sql_thrash_respects_limit_env(monkeypatch) -> None:
    from duckclaw.workers import sql_thrash as mod

    monkeypatch.setenv("DUCKCLAW_READ_SQL_THRASH_LIMIT", "2")
    assert mod.is_sql_thrash(_msgs_with_sql(1)) is False
    assert mod.is_sql_thrash(_msgs_with_sql(2)) is True


def test_clear_sql_forces_if_thrash() -> None:
    from duckclaw.workers.sql_thrash import clear_sql_forces_if_thrash

    orch, fs, fa, fr = clear_sql_forces_if_thrash(
        _msgs_with_sql(3),
        force_orch_tool="read_sql",
        force_schema=True,
        force_admin_sql=True,
        force_read_sql=True,
    )
    assert orch is None
    assert fs is False and fa is False and fr is False

    orch2, *_rest = clear_sql_forces_if_thrash(
        _msgs_with_sql(1),
        force_orch_tool="read_sql",
        force_schema=False,
        force_admin_sql=False,
        force_read_sql=True,
    )
    assert orch2 == "read_sql"
    assert _rest[-1] is True


def test_strip_and_maybe_apply_guard() -> None:
    from duckclaw.workers.sql_thrash import maybe_apply_sql_thrash_tool_guard, strip_sql_tools

    tools = [
        SimpleNamespace(name="read_sql"),
        SimpleNamespace(name="tavily_search"),
        SimpleNamespace(name="admin_sql"),
        SimpleNamespace(name="invoke_worker"),
    ]
    stripped = strip_sql_tools(tools)
    assert [t.name for t in stripped] == ["tavily_search", "invoke_worker"]

    out, applied, det = maybe_apply_sql_thrash_tool_guard(tools, _msgs_with_sql(3))
    assert applied is True
    assert det and "SQL_THRASH_DETENTE" in det
    assert all(t.name not in {"read_sql", "admin_sql", "inspect_schema"} for t in out)

    out2, applied2, det2 = maybe_apply_sql_thrash_tool_guard(tools, _msgs_with_sql(1))
    assert applied2 is False and det2 is None
    assert len(out2) == len(tools)


def test_apply_terminal_clears_force_read_sql_on_thrash() -> None:
    from duckclaw.workers.factory_graph_nodes_agent_policy_early_context import (
        apply_terminal_force_tool_overrides,
    )

    (
        orch,
        force_schema,
        force_admin,
        force_read,
        *_rest,
    ) = apply_terminal_force_tool_overrides(
        incoming="profundiza NVDA OHLCV",
        orch_incoming="profundiza NVDA OHLCV",
        intent_incoming="profundiza NVDA OHLCV",
        tools_by_name={"read_sql": object(), "tavily_search": object()},
        called_tools_since_last_human={"read_sql"},  # set alone is not enough
        already_has_tool_result=True,
        telegram_context_summarize_directive=False,
        summarize_stored_directive=False,
        use_heuristic_first_tool=True,
        force_orch_tool="read_sql",
        force_schema=False,
        force_admin_sql=False,
        force_read_sql=True,
        force_tavily=False,
        force_reddit=False,
        force_visual=False,
        messages=_msgs_with_sql(3),
    )
    assert force_read is False
    assert force_admin is False
    assert orch is None
    assert force_schema is False


def test_apply_auto_bind_tool_guards_injects_detente() -> None:
    from duckclaw.workers.sql_thrash import apply_auto_bind_tool_guards

    tools = [
        SimpleNamespace(name="read_sql"),
        SimpleNamespace(name="tavily_search"),
    ]
    llm_msgs = [HumanMessage(content="hi")]
    groq = [HumanMessage(content="hi")]
    out_tools, rebind, out_msgs, out_groq, thrash = apply_auto_bind_tool_guards(
        tools,
        _msgs_with_sql(3),
        loop_system_event=False,
        llm_messages=llm_msgs,
        groq_messages=groq,
    )
    assert thrash is True and rebind is True
    assert [t.name for t in out_tools] == ["tavily_search"]
    assert isinstance(out_msgs[0], SystemMessage)
    assert "SQL_THRASH_DETENTE" in str(out_msgs[0].content)
    assert out_groq is not None and out_groq[0] is out_msgs[0]
