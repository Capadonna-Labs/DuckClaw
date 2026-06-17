from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHS_ROOT = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs"
GRAPH_FACADE = GRAPHS_ROOT / "graph_server.py"
MAX_FACADE_LINES = 400
MAX_MODULE_LINES = 500

GRAPH_SERVER_SPLIT_MODULES = (
    "graph_server_llm_config.py",
    "graph_server_studio.py",
    "graph_server_invoke.py",
    "graph_server_routes.py",
    "graph_server_ephemeral.py",
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _facade_function_names() -> set[str]:
    tree = ast.parse(GRAPH_FACADE.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_graph_server_facade_is_thin() -> None:
    assert _line_count(GRAPH_FACADE) <= MAX_FACADE_LINES


def test_graph_server_studio_owns_get_graph() -> None:
    import importlib

    facade = importlib.import_module("duckclaw.graphs.graph_server")
    studio = importlib.import_module("duckclaw.graphs.graph_server_studio")

    assert facade.get_graph is studio.get_graph
    assert studio.get_graph.__module__ == "duckclaw.graphs.graph_server_studio"
    assert "get_graph" not in _facade_function_names()


def test_graph_server_llm_config_owns_ensure_llm_config() -> None:
    import importlib

    facade = importlib.import_module("duckclaw.graphs.graph_server")
    llm_config = importlib.import_module("duckclaw.graphs.graph_server_llm_config")

    assert facade._ensure_llm_config is llm_config._ensure_llm_config
    assert llm_config._ensure_llm_config.__module__ == "duckclaw.graphs.graph_server_llm_config"
    assert "_ensure_llm_config" not in _facade_function_names()


def test_graph_server_invoke_owns_ainvoke_manager_ephemeral() -> None:
    import importlib

    facade = importlib.import_module("duckclaw.graphs.graph_server")
    invoke = importlib.import_module("duckclaw.graphs.graph_server_invoke")

    assert facade.ainvoke_manager_ephemeral is invoke.ainvoke_manager_ephemeral
    assert invoke.ainvoke_manager_ephemeral.__module__ == "duckclaw.graphs.graph_server_invoke"
    assert "ainvoke_manager_ephemeral" not in _facade_function_names()


def test_graph_server_split_modules_exist_and_respect_line_budget() -> None:
    over_budget: list[str] = []
    for name in GRAPH_SERVER_SPLIT_MODULES:
        path = GRAPHS_ROOT / name
        assert path.is_file(), name
        count = _line_count(path)
        if count > MAX_MODULE_LINES:
            over_budget.append(f"{name}: {count} lines")
    assert over_budget == [], f"modules over {MAX_MODULE_LINES} lines: {over_budget}"


def test_graph_server_facade_has_no_route_handler_defs() -> None:
    source = GRAPH_FACADE.read_text(encoding="utf-8")
    for marker in (
        "@app.get(",
        "@app.post(",
        "async def invoke(",
        "async def stream(",
        "async def graph_info(",
        "class InvokeRequest",
    ):
        assert marker not in source
