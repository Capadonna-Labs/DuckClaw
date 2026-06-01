from __future__ import annotations

import importlib
from pathlib import Path


def test_shared_layer_facades_expose_existing_public_contracts() -> None:
    modules = {
        "duckclaw.config.gateway_port": "resolve_gateway_port",
        "duckclaw.config.runtime_env": "resolve_redis_url",
        "duckclaw.config.env_secrets": "is_secret_env_key",
        "duckclaw.storage.gateway_db": "get_gateway_db_path",
        "duckclaw.storage.vaults": "resolve_active_vault",
        "duckclaw.storage.shared_db_grants": "list_shared_grants_for_tenant",
        "duckclaw.storage.db_write_queue": "enqueue_duckdb_write_sync",
        "duckclaw.storage.bootstrap_core": "bootstrap_core_schema",
        "duckclaw.control_plane.admin_console_users": "ensure_admin_console_users_table",
        "duckclaw.control_plane.admin_worker_catalog": "ensure_admin_worker_catalog_schema",
        "duckclaw.control_plane.admin_workspace": "ensure_admin_workspace_schema",
        "duckclaw.llm.providers": "build_llm",
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
        root / "prompts" / "synthetic" / "pqrsd_gemma4_jsonl.md",
        root / "scripts" / "data" / "curate_traces.py",
        root / "scripts" / "serve" / "start_mlx.sh",
        root / "scripts" / "serve" / "start_mlx_vision.sh",
        root / "scripts" / "serve" / "run_mlx_lm_server.py",
        root / "datasets" / "README.md",
        root / "outputs" / "README.md",
    )
    for path in expected:
        assert path.exists(), path
