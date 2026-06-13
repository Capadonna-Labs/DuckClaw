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
    modules = {
        "duckclaw.runtime.graph_server": "get_graph",
        "duckclaw.runtime.commands": "handle_command",
        "duckclaw.runtime.sandbox": "_sandbox_stdout_suggests_success_despite_exit",
        "duckclaw.runtime.heartbeat": "normalize_telegram_chat_id_for_outbound",
        "duckclaw.runtime.conversation_traces": "append_conversation_trace",
        "duckclaw.manager.graph": "build_manager_graph",
        "duckclaw.manager.routing": "clear_worker_graph_cache",
    }
    for module_name, attr in modules.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, attr), module_name


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
