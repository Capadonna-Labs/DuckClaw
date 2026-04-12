"""Heurísticas de follow-up a memoria semántica (superficie de tools liviana)."""

from __future__ import annotations

import pytest

from duckclaw.graphs.manager_graph import (
    _incoming_looks_like_semantic_context_followup,
    _worker_should_use_lite_stdio_mcp_surface,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hay algo sobre Elon Musk en el contexto?", True),
        ("¿Qué hay anotado sobre SpaceX?", True),
        ("notas sobre dividendos en la memoria", True),
        ("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nhttps://x.com/foo", False),
        ("Cuéntame el precio de AAPL hoy", False),
        ("noticias de la Fed", False),
    ],
)
def test_incoming_looks_like_semantic_context_followup(text: str, expected: bool) -> None:
    assert _incoming_looks_like_semantic_context_followup(text) is expected


def test_worker_lite_surface_true_for_summarize_directive() -> None:
    body = "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nhttps://example.com/a"
    assert _worker_should_use_lite_stdio_mcp_surface(body) is True


def test_worker_lite_surface_true_for_semantic_question() -> None:
    assert _worker_should_use_lite_stdio_mcp_surface("hay algo sobre Tesla en el contexto?") is True


def test_worker_lite_surface_false_for_unrelated() -> None:
    assert _worker_should_use_lite_stdio_mcp_surface("resumen de mercado SPX") is False
