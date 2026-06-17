from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_ROOT = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "manager"
GRAPH_FACADE = MANAGER_ROOT / "graph.py"
GRAPH_BUILDER = MANAGER_ROOT / "manager_graph_builder.py"
MAX_FACADE_LINES = 300
MAX_MODULE_LINES = 500

MANAGER_SPLIT_MODULES = (
    "manager_worker_cache.py",
    "manager_vault_config.py",
    "manager_entry_routes.py",
    "manager_mercenary_policy.py",
    "manager_plan_task.py",
    "manager_planner_llm.py",
    "manager_delegation.py",
    "manager_invoke_helpers.py",
    "manager_graph_routing.py",
    "manager_nodes_router.py",
    "manager_nodes_greeting.py",
    "manager_nodes_plan.py",
    "manager_nodes_invoke.py",
    "manager_nodes_mercenary.py",
    "manager_nodes_return.py",
    "manager_graph_builder.py",
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _facade_function_names() -> set[str]:
    tree = ast.parse(GRAPH_FACADE.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_manager_graph_facade_is_thin() -> None:
    assert _line_count(GRAPH_FACADE) <= MAX_FACADE_LINES


def test_manager_graph_builder_owns_build_manager_graph() -> None:
    import importlib

    facade = importlib.import_module("duckclaw.manager.graph")
    builder = importlib.import_module("duckclaw.manager.manager_graph_builder")

    assert facade.build_manager_graph is builder.build_manager_graph
    assert builder.build_manager_graph.__module__ == "duckclaw.manager.manager_graph_builder"
    assert "build_manager_graph" not in _facade_function_names()


def test_manager_split_modules_exist_and_respect_line_budget() -> None:
    over_budget: list[str] = []
    for name in MANAGER_SPLIT_MODULES:
        path = MANAGER_ROOT / name
        assert path.is_file(), name
        count = _line_count(path)
        if count > MAX_MODULE_LINES:
            over_budget.append(f"{name}: {count} lines")
    assert over_budget == [], f"modules over {MAX_MODULE_LINES} lines: {over_budget}"


def test_manager_graph_facade_has_no_node_handler_defs() -> None:
    source = GRAPH_FACADE.read_text(encoding="utf-8")
    for marker in (
        "def router_node",
        "def plan_node",
        "def invoke_worker_node",
        "def mercenary_node",
        "def return_to_source_node",
        "StateGraph(",
    ):
        assert marker not in source
