"""Turnos con adjuntos no deben convertirse en tareas enlatadas de DuckDB."""

from __future__ import annotations

from duckclaw.manager.manager_plan_task import _plan_task

_ATTACHMENT_TURN = (
    "[PROJECT_CONTEXT]\n"
    "Nombre: Finanz 1\n"
    "Descripcion: analisis financiero\n\n"
    "[DOCUMENTOS_ADJUNTOS]\n"
    "[Documento adjunto: 2026 MOVIMIENTOS CONTABILIDAD.xlsx "
    "path=C:\\Users\\Usuario\\AppData\\Local\\DuckClaw\\db\\private\\user-x\\inbound\\mov.xlsx]\n"
    "Fecha;Concepto;Datos\n"
    "2026-01-02;Nomina;1200\n\n"
    "--- Mensaje del usuario ---\n"
    "revisa este archivo excel"
)


def test_attachment_turn_keeps_user_message():
    planned, override = _plan_task(_ATTACHMENT_TURN, "finanz-expert")
    assert override is None
    assert planned == _ATTACHMENT_TURN.strip()
    assert "get_db_path" not in planned
    assert "TAREA:" not in planned


def test_attachment_turn_with_explicit_db_question_still_plans_db_task():
    turn = _ATTACHMENT_TURN.replace(
        "revisa este archivo excel",
        "que tablas hay en la base de datos duckdb",
    )
    planned, _ = _plan_task(turn, "finanz-expert")
    assert planned != turn.strip()


def test_plain_db_question_without_attachments_still_plans_db_task():
    planned, _ = _plan_task("cual es el nombre de la base de datos", "finanz-expert")
    assert "get_db_path" in planned
