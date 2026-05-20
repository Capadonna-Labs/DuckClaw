"""Smoke: guardrails referenciados en factory y manager existen en disco."""

from __future__ import annotations

import pytest

from duckclaw.guardrails.loader import (
    format_guardrail,
    load_guardrail,
    load_guardrail_kv,
    load_guardrail_pipe_table,
    load_guardrail_task_list,
)

_REQUIRED = [
    ("prompts", "task_awareness_default"),
    ("prompts", "task_awareness_axis"),
    ("directives", "pqrsd_datos_primero"),
    ("directives", "tool_choice_generic"),
    ("directives", "quant_autoexec"),
    ("directives", "quant_ohlcv_moc"),
    ("directives", "quant_pipeline_deterministic"),
    ("directives", "reddit_share_exhausted"),
    ("errors", "llm_failure_mlx"),
    ("errors", "llm_failure_groq_tpm"),
    ("errors", "llm_failure_groq_generic"),
    ("errors", "llm_failure_deepseek"),
    ("errors", "llm_failure_openai"),
    ("errors", "llm_failure_generic"),
    ("manager_tasks", "finanz_tool_pressure"),
    ("manager_tasks", "quant_hrp_affirm_planned"),
    ("manager_tasks", "quant_hrp_affirm_task_confirm"),
    ("manager_tasks", "quant_hrp_affirm_task_flow"),
    ("manager_tasks", "quant_operational_fly_command"),
    ("manager_tasks", "bi_analyst_capabilities_question"),
    ("manager_tasks", "job_opportunity_tracking"),
    ("manager_tasks", "job_application_tracking"),
    ("manager_tasks", "job_income_injection"),
    ("manager_tasks", "duckdb_name_query"),
    ("manager_tasks", "table_content_named"),
    ("manager_tasks", "table_content_generic"),
    ("manager_tasks", "list_database_tables"),
    ("manager_tasks", "job_track_synthesis_finanz"),
    ("manager_tasks", "job_income_synthesis_finanz"),
    ("capabilities", "axis_coordinator"),
    ("capabilities", "job_hunter"),
    ("capabilities", "bi_analyst"),
    ("capabilities", "finanz"),
    ("capabilities", "axis_maestro"),
    ("capabilities", "siata_analyst"),
    ("capabilities", "generic_worker"),
    ("capabilities", "default_fallback"),
    ("planner_tasks", "summarize_new_context_title"),
    ("planner_tasks", "summarize_stored_context_title"),
    ("resilience", "replan_task_suffix"),
    ("resilience", "exhausted_plan_failure"),
    ("heartbeat", "tool_steps"),
    ("system_prompts", "general_default"),
    ("system_prompts", "retail_default"),
    ("system_prompts", "dreamer_consolidation"),
    ("validators", "fact_checker"),
    ("validators", "self_correction"),
    ("fly_commands", "help_header"),
    ("fly_commands", "roles_list_intro"),
    ("fly_commands", "workers_list_hint"),
]


@pytest.mark.parametrize("parts", _REQUIRED, ids=lambda p: "/".join(p))
def test_guardrail_files_exist(parts: tuple[str, str]) -> None:
    text = load_guardrail(*parts)
    assert len(text) > 20, f"guardrail vacío: {parts}"


def test_format_guardrail_table_name() -> None:
    out = format_guardrail("manager_tasks", "table_content_named", table_name="finance_worker.cuentas")
    assert "finance_worker.cuentas" in out


def test_format_guardrail_job_tracking_context() -> None:
    out = format_guardrail("manager_tasks", "job_opportunity_tracking", context="https://example.com/job")
    assert "https://example.com/job" in out


def test_summarize_new_context_task_list() -> None:
    tasks = load_guardrail_task_list("planner_tasks", "summarize_new_context_tasks")
    assert len(tasks) == 5
    assert "CONTEXT_ANCLA_TIEMPO" in tasks[1]
    assert "get_current_time" in tasks[4]


def test_summarize_stored_context_task_list() -> None:
    tasks = load_guardrail_task_list("planner_tasks", "summarize_stored_context_tasks")
    assert len(tasks) == 4
    assert "semantic_memory" in tasks[0]


def test_llm_plan_summarize_new_context() -> None:
    from duckclaw.graphs.manager_graph import _llm_plan

    title, tasks = _llm_plan("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nbody")
    assert title == "Síntesis de contexto (recién inyectado)"
    assert len(tasks) == 5


def test_heartbeat_tool_steps() -> None:
    from duckclaw.graphs.chat_heartbeat import heartbeat_message_for_tool

    assert "read_sql" in heartbeat_message_for_tool("read_sql")
    assert "foo_tool" in heartbeat_message_for_tool("foo_tool")


def test_help_pipe_table() -> None:
    rows = load_guardrail_pipe_table("fly_commands", "help_entries")
    assert any(cmd == "/team" for cmd, _ in rows)
    assert len(rows) >= 30


def test_execute_help() -> None:
    from duckclaw.graphs.on_the_fly_commands import execute_help

    out = execute_help(None, "1")
    assert "Fly commands" in out
    assert "/quant_cycle" in out


def test_replan_suffix_format() -> None:
    from duckclaw.graphs.agent_resilience import format_replan_task_suffix

    s = format_replan_task_suffix(1, 3)
    assert "[REPLAN intento 2/3]" in s
    assert "read_sql" in s
