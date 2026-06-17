"""Smoke tests for entry router: build_entry_router_graph."""

from __future__ import annotations

from unittest.mock import MagicMock

from duckclaw.graphs.router import build_entry_router_graph


def test_router_imports() -> None:
    from duckclaw.graphs import build_entry_router_graph as build_graph

    assert callable(build_graph)


def test_build_entry_router_graph_smoke() -> None:
    """Build entry router graph with a mock LLM (no API required)."""
    mock_llm = MagicMock()
    db = MagicMock()
    graph = build_entry_router_graph(db, mock_llm, system_prompt="Test.")
    assert graph is not None
