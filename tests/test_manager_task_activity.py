from __future__ import annotations

from duckclaw.manager.task_activity import (
    _activity_task_for_plan,
    _append_task_audit_safely,
    _task_summary_for_activity,
    _worker_tool_names_from_messages,
)


def test_task_summary_for_activity_detects_database_name_requests() -> None:
    assert (
        _task_summary_for_activity("cual es el nombre de la db que tienes disponible?", "")
        == "Buscando el nombre de la db disponible."
    )


def test_task_summary_for_activity_detects_schema_requests() -> None:
    assert (
        _task_summary_for_activity("que tablas hay disponibles?", "")
        == "Listando tablas de la base de datos."
    )


def test_task_summary_for_activity_truncates_long_incoming() -> None:
    incoming = "Resume esta solicitud con suficiente detalle para que el worker no vea todo"

    assert _task_summary_for_activity(incoming, "") == incoming[:48] + "\u2026"


def test_activity_task_for_plan_prefers_clean_plan_title() -> None:
    assert _activity_task_for_plan("  Revisar contrato  ", "Resumen fallback") == "Revisar contrato"


def test_activity_task_for_plan_uses_summary_without_title() -> None:
    assert _activity_task_for_plan("", "Resumen fallback") == "Resumen fallback"


def test_worker_tool_names_from_messages_uses_only_current_turn() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "old_tool"}}],
        },
        {"role": "user", "content": "consulta la tabla"},
        {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "read_sql"}}],
        },
        {"role": "tool", "name": "read_sql", "content": "[]"},
    ]

    assert _worker_tool_names_from_messages(messages) == ["read_sql"]


def test_worker_tool_names_from_messages_extracts_embedded_tool_json() -> None:
    messages = [
        {"role": "user", "content": "consulta SQL"},
        {
            "role": "assistant",
            "content": 'Voy a consultar:\n{"name": "read_sql", "arguments": {"query": "select 1"}}',
        },
    ]

    assert _worker_tool_names_from_messages(messages) == ["read_sql"]


def test_append_task_audit_safely_suppresses_audit_failures() -> None:
    calls: list[tuple[object, ...]] = []

    def append_task_audit(*args: object, **kwargs: object) -> None:
        calls.append(args + (kwargs,))
        raise RuntimeError("audit unavailable")

    ok = _append_task_audit_safely(
        append_task_audit,
        db=object(),
        chat_id="chat-1",
        worker_id="manager",
        incoming="hola",
        status="SUCCESS",
        elapsed_ms=0,
        plan_title="Saludo directo",
    )

    assert ok is False
    assert len(calls) == 1
