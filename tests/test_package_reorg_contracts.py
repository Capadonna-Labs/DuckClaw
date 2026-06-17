from __future__ import annotations

import importlib
from pathlib import Path


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
    )
    for module_name, attr in modules:
        module = importlib.import_module(module_name)
        assert hasattr(module, attr), module_name


def test_manager_graph_implementation_is_owned_by_manager_package() -> None:
    manager_graph = importlib.import_module("duckclaw.manager.graph")
    legacy_graph = importlib.import_module("duckclaw.graphs.manager_graph")
    builder = importlib.import_module("duckclaw.manager.manager_graph_builder")

    assert manager_graph.build_manager_graph is builder.build_manager_graph
    assert builder.build_manager_graph.__module__ == "duckclaw.manager.manager_graph_builder"
    assert legacy_graph.build_manager_graph is manager_graph.build_manager_graph


def test_homeostasis_goals_alignment_implementation_is_owned_by_homeostasis_package() -> None:
    legacy_goals_alignment = importlib.import_module("duckclaw.forge.homeostasis.goals_alignment")

    assert (
        legacy_goals_alignment.assess_goals_alignment.__module__
        == "duckclaw.homeostasis.goals_alignment"
    )
    canonical_goals_alignment = importlib.import_module(
        legacy_goals_alignment.assess_goals_alignment.__module__
    )
    assert legacy_goals_alignment.assess_goals_alignment is canonical_goals_alignment.assess_goals_alignment


def test_homeostasis_runtime_implementations_are_owned_by_homeostasis_package() -> None:
    canonical_surprise = importlib.import_module("duckclaw.homeostasis.surprise")
    canonical_beliefs = importlib.import_module("duckclaw.homeostasis.belief_registry")
    canonical_manager = importlib.import_module("duckclaw.homeostasis.manager")

    legacy_surprise = importlib.import_module("duckclaw.forge.homeostasis.surprise")
    legacy_beliefs = importlib.import_module("duckclaw.forge.homeostasis.belief_registry")
    legacy_manager = importlib.import_module("duckclaw.forge.homeostasis.manager")

    assert canonical_surprise.compute_surprise.__module__ == "duckclaw.homeostasis.surprise"
    assert legacy_surprise.compute_surprise is canonical_surprise.compute_surprise
    assert legacy_surprise.SurpriseResult is canonical_surprise.SurpriseResult

    assert canonical_beliefs.BeliefRegistry.__module__ == "duckclaw.homeostasis.belief_registry"
    assert legacy_beliefs.BeliefRegistry is canonical_beliefs.BeliefRegistry
    assert legacy_beliefs.load_beliefs_from_config is canonical_beliefs.load_beliefs_from_config

    assert canonical_manager.HomeostasisManager.__module__ == "duckclaw.homeostasis.manager"
    assert legacy_manager.HomeostasisManager is canonical_manager.HomeostasisManager


def test_singleton_writer_implementation_is_owned_by_shared_db_write_queue() -> None:
    canonical_writer = importlib.import_module("duckclaw.db_write_queue")
    legacy_writer = importlib.import_module("duckclaw.forge.homeostasis.singleton_writer")

    for attr in (
        "enqueue_write",
        "execute_write_direct",
        "WriteQueueBridge",
        "run_consumer",
    ):
        legacy_symbol = getattr(legacy_writer, attr)
        canonical_symbol = getattr(canonical_writer, attr)
        assert legacy_symbol is canonical_symbol
        assert legacy_symbol.__module__ == "duckclaw.db_write_queue"


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
