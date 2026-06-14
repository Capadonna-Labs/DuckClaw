from __future__ import annotations

import pytest

from duckclaw.manager.task_classification import (
    _incoming_looks_like_semantic_context_followup,
    _job_hunter_user_requests_application_tracking,
    _user_signals_cashflow_stress,
    _worker_should_use_lite_stdio_mcp_surface,
    job_hunter_user_requests_job_search,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hay algo sobre Tesla en el contexto?", True),
        ("notas sobre dividendos en la memoria", True),
        ("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nhttps://example.com/a", False),
        ("resumen de mercado SPX", False),
    ],
)
def test_semantic_context_followup_classification(text: str, expected: bool) -> None:
    assert _incoming_looks_like_semantic_context_followup(text) is expected


def test_lite_stdio_surface_covers_context_directives_and_followups() -> None:
    assert _worker_should_use_lite_stdio_mcp_surface("[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]") is True
    assert _worker_should_use_lite_stdio_mcp_surface("¿qué hay anotado en mi contexto?") is True
    assert _worker_should_use_lite_stdio_mcp_surface("noticias de la Fed") is False


def test_job_search_classification_excludes_tracking_and_add_commands() -> None:
    assert job_hunter_user_requests_job_search("Busca vacantes remotas de data scientist") is True
    assert job_hunter_user_requests_job_search("/job --add https://example.com/job") is False
    assert job_hunter_user_requests_job_search("dame seguimiento de mis postulaciones") is False


def test_application_tracking_and_cashflow_classification() -> None:
    assert _job_hunter_user_requests_application_tracking("estado de mis postulaciones a vacantes") is True
    assert _user_signals_cashflow_stress("estoy sin liquidez y necesito ingreso extra") is True
    assert _user_signals_cashflow_stress("analiza flujo de caja de esta empresa") is False
