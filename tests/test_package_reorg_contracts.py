from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_shared_layer_flat_modules_expose_public_contracts() -> None:
    modules = {
        "duckclaw.gateway_port": "resolve_gateway_port",
        "duckclaw.runtime_env": "resolve_redis_url",
        "duckclaw.env_secrets": "is_secret_env_key",
        "duckclaw.gateway_db": "get_gateway_db_path",
        "duckclaw.vaults": "resolve_active_vault",
        "duckclaw.shared_db_grants": "list_shared_grants_for_tenant",
        "duckclaw.db_write_queue": "enqueue_duckdb_write_sync",
        "duckclaw.bootstrap_core": "bootstrap_core_schema",
        "duckclaw.admin_console_users": "ensure_admin_console_users_table",
        "duckclaw.admin_worker_catalog": "ensure_admin_worker_catalog_schema",
        "duckclaw.admin_workspace": "ensure_admin_workspace_schema",
        "duckclaw.integrations.llm_providers": "build_llm",
    }
    for module_name, attr in modules.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, attr), module_name


def test_duckclaw_namespace_merges_core_and_shared() -> None:
    import duckclaw
    from duckclaw.db_bridge import DuckClaw as BridgeDuckClaw

    assert duckclaw.DuckClaw is BridgeDuckClaw
    assert len(duckclaw.__path__) >= 2
    importlib.import_module("duckclaw.duckdb_read_compat")


def test_agents_runtime_and_manager_facades_expose_public_contracts() -> None:
    modules = (
        ("duckclaw.runtime.graph_server", "get_graph"),
        ("duckclaw.runtime.commands", "handle_command"),
        ("duckclaw.runtime.sandbox", "_sandbox_stdout_suggests_success_despite_exit"),
        ("duckclaw.runtime.heartbeat", "normalize_telegram_chat_id_for_outbound"),
        ("duckclaw.runtime.conversation_traces", "append_conversation_trace"),
        ("duckclaw.manager.graph", "build_manager_graph"),
        ("duckclaw.manager.routing", "clear_worker_graph_cache"),
        ("duckclaw.manager.routing", "_worker_matches_id"),
        ("duckclaw.manager.fast_plans", "_try_capability_fast_plan"),
        ("duckclaw.manager.task_classification", "_worker_should_use_lite_stdio_mcp_surface"),
        ("duckclaw.manager.planning", "_plan_task"),
        ("duckclaw.traces", "TraceCollector"),
        ("duckclaw.train", "MlxSFT"),
    )
    for module_name, attr in modules:
        module = importlib.import_module(module_name)
        assert hasattr(module, attr), module_name


def test_manager_graph_implementation_is_owned_by_manager_package() -> None:
    manager_graph = importlib.import_module("duckclaw.manager.graph")
    builder = importlib.import_module("duckclaw.manager.manager_graph_builder")

    assert manager_graph.build_manager_graph is builder.build_manager_graph
    assert builder.build_manager_graph.__module__ == "duckclaw.manager.manager_graph_builder"
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("duckclaw.graphs.manager_graph")
    assert not Path("packages/agents/src/duckclaw/graphs/manager_graph.py").exists()


def test_tests_do_not_import_task_classification_from_legacy_manager_graph() -> None:
    """Task classification moved to ``duckclaw.manager.task_classification`` (not the graph facade)."""
    import ast

    tests_dir = Path("tests")
    banned = frozenset(
        {
            "_incoming_looks_like_semantic_context_followup",
            "_worker_should_use_lite_stdio_mcp_surface",
            "_incoming_has_context_summary_system_directive",
        }
    )
    offenders: list[str] = []
    current = Path(__file__).resolve()
    for path in sorted(tests_dir.rglob("test_*.py")):
        if path.resolve() == current:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module not in {"duckclaw.graphs.manager_graph", "duckclaw.manager.graph"}:
                continue
            if node.module == "duckclaw.graphs.manager_graph":
                offenders.append(f"{path}:{node.lineno}: legacy manager_graph import")
                continue
            for alias in node.names:
                if alias.name in banned:
                    offenders.append(f"{path}:{node.lineno}: {alias.name}")
    assert offenders == [], f"Use duckclaw.manager.task_classification: {offenders}"


def test_forge_homeostasis_shims_are_removed() -> None:
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("duckclaw.forge.homeostasis")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("duckclaw.forge.homeostasis.singleton_writer")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("duckclaw.api")

    assert not Path("packages/agents/src/duckclaw/forge/homeostasis").exists()
    assert not Path("packages/agents/src/duckclaw/api").exists()

    canonical = importlib.import_module("duckclaw.homeostasis.manager")
    assert hasattr(canonical, "HomeostasisManager")
    writer = importlib.import_module("duckclaw.db_write_queue")
    assert hasattr(writer, "enqueue_write")


def test_training_layout_has_separate_prompt_script_and_dataset_roots() -> None:
    root = Path("packages/agents/train")
    expected = (
        root / "scripts" / "data" / "curate_traces.py",
        root / "scripts" / "serve" / "start_mlx.sh",
        root / "scripts" / "serve" / "start_mlx_vision.sh",
        root / "scripts" / "serve" / "run_mlx_lm_server.py",
        root / "datasets" / "README.md",
        root / "outputs" / "README.md",
    )
    for path in expected:
        assert path.exists(), path
