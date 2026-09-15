"""Smoke tests for entry router: build_entry_router_graph."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from duckclaw.graphs.router import build_entry_router_graph


def test_router_imports() -> None:
    from duckclaw.graphs import build_entry_router_graph as build_graph

    assert callable(build_graph)


def _stub_llm() -> SimpleNamespace:
    """Avoid bare MagicMock LLMs: OpenRouter walkers treat .bound as infinite."""

    def bind_tools(tools, **kwargs):  # noqa: ANN001, ANN003
        return SimpleNamespace(bind_tools=bind_tools, tools=list(tools), kwargs=dict(kwargs))

    return SimpleNamespace(bind_tools=bind_tools, model_name="stub-llm")


@pytest.mark.smoke
def test_build_entry_router_graph_smoke() -> None:
    """Build entry router graph with a stub LLM (no API required)."""
    graph = build_entry_router_graph(MagicMock(), _stub_llm(), system_prompt="Test.")
    assert graph is not None
