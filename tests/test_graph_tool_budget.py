"""Graph tool-round / recursion budget defaults."""

from __future__ import annotations

import os

from duckclaw.utils.langsmith_trace import (
    DEFAULT_GRAPH_RECURSION_LIMIT,
    get_tracing_config,
    resolve_graph_recursion_limit,
    with_graph_recursion_limit,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext


def test_default_max_tool_rounds_is_75() -> None:
    assert WorkerGraphContext().max_tool_rounds == 75


def test_resolve_graph_recursion_limit_default(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_GRAPH_RECURSION_LIMIT", raising=False)
    assert resolve_graph_recursion_limit() == DEFAULT_GRAPH_RECURSION_LIMIT
    assert DEFAULT_GRAPH_RECURSION_LIMIT >= 2 * 75


def test_resolve_graph_recursion_limit_env(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_GRAPH_RECURSION_LIMIT", "200")
    assert resolve_graph_recursion_limit() == 200


def test_get_tracing_config_includes_recursion_limit(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_GRAPH_RECURSION_LIMIT", raising=False)
    cfg = get_tracing_config("t1", "quant-trader", "chat-1")
    assert cfg["recursion_limit"] == DEFAULT_GRAPH_RECURSION_LIMIT


def test_with_graph_recursion_limit_never_lowers(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_GRAPH_RECURSION_LIMIT", "80")
    assert with_graph_recursion_limit({"recursion_limit": 200})["recursion_limit"] == 200
    assert with_graph_recursion_limit(None)["recursion_limit"] == 80
