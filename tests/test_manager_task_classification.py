from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.manager.task_classification import (
    _incoming_looks_like_semantic_context_followup,
    _worker_should_use_lite_stdio_mcp_surface,
)


TASK_CLASSIFICATION_PATH = Path("packages/agents/src/duckclaw/manager/task_classification.py")


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


def test_task_classification_has_no_hardcoded_vertical_policy() -> None:
    source = TASK_CLASSIFICATION_PATH.read_text(encoding="utf-8").lower()
    banned_markers = (
        "job",
        "career",
        "empleo",
        "trabajo",
        "vacante",
        "postul",
        "finanz",
        "quant",
        "pqrs",
        "leila",
        "war_room",
    )
    offenders = [marker for marker in banned_markers if marker in source]

    assert offenders == []


def test_vertical_phrases_are_not_special_cased_by_manager_classifier() -> None:
    assert _worker_should_use_lite_stdio_mcp_surface("Busca vacantes remotas de data scientist") is False
    assert _worker_should_use_lite_stdio_mcp_surface("/job --add https://example.com/job") is False
    assert _worker_should_use_lite_stdio_mcp_surface("dame seguimiento de mis postulaciones") is False
