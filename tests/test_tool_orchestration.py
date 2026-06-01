"""Tests for manifest-driven tool orchestration (generic motor, finanz fixture)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.manifest import load_manifest
from duckclaw.workers.tool_orchestration import (
    affirm_followup_planned_task,
    match_intent,
    parse_tool_orchestration,
    replan_rule_triggered,
    resolve_forced_tool,
)


def _finanz_orch():
    spec = load_manifest("finanz")
    orch = parse_tool_orchestration(spec)
    assert orch is not None
    return spec, orch


def test_ledger_read_after_get_current_time_chains_read_sql():
    _, orch = _finanz_orch()
    incoming = "Dame un resumen de mis deudas"
    tools = {"get_current_time": object(), "read_sql": object(), "admin_sql": object()}
    messages = [
        HumanMessage(content=incoming),
        AIMessage(content="", tool_calls=[{"name": "get_current_time", "id": "1", "args": {}}]),
        ToolMessage(content='{"date":"2026-05-20"}', name="get_current_time", tool_call_id="1"),
    ]
    forced = resolve_forced_tool(orch, incoming, messages, tools)
    assert forced == "read_sql"


def test_ledger_write_first_step_clock_anchor():
    _, orch = _finanz_orch()
    incoming = "Agrega 50k deuda mamá Mayo"
    tools = {"get_current_time": object(), "read_sql": object(), "admin_sql": object()}
    forced = resolve_forced_tool(orch, incoming, [HumanMessage(content=incoming)], tools)
    assert forced == "get_current_time"


def test_ledger_write_intent_matches_admin_sql_path():
    _, orch = _finanz_orch()
    incoming = "Agrega 50k deuda mamá Mayo"
    assert match_intent(incoming, orch) == "ledger_write"


def test_affirm_followup_planned_task_from_guardrail():
    spec, orch = _finanz_orch()
    incoming = "Procede"
    history = [
        {
            "role": "assistant",
            "content": "Estas son las acciones que voy a realizar con admin_sql: aumentar deuda mamá.",
        }
    ]
    planned = affirm_followup_planned_task(orch, incoming, history, spec.worker_dir)
    assert planned
    assert "admin_sql" in planned.lower()
    assert "TAREA" in planned or "mutaciones" in planned.lower()


def test_replan_when_write_intent_without_admin_sql():
    _, orch = _finanz_orch()
    incoming = "Agrega 50k deuda mamá"
    triggered, reason = replan_rule_triggered(orch, incoming, ["read_sql", "get_current_time"])
    assert triggered is True
    assert "admin_sql" in reason
