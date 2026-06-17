from __future__ import annotations

import importlib
import inspect

import duckclaw
from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.model_setup"
MODEL_SETUP_FUNCTION_EXPORTS = (
    "_debug_log_model_config",
    "get_effective_system_prompt",
    "_effective_llm_triplet_for_chat_ui",
    "chat_has_llm_chat_state_override",
    "resolve_llm_triplet_for_chat_invocation",
    "execute_model",
    "_parse_pipe_kv_args",
    "_gemini_models_list_from_api",
    "execute_models",
    "execute_prompt",
    "execute_setup",
    "_execute_setup",
)
MODEL_SETUP_CONSTANT_EXPORTS = (
    "_PROVIDERS",
    "_DEFAULT_MODEL_BY_PROVIDER",
    "_DEFAULT_BASE_URL_BY_PROVIDER",
)


def test_model_setup_command_ownership_lives_outside_graphs() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)

    for name in MODEL_SETUP_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE
        assert exported is getattr(model_setup, name)
    for name in MODEL_SETUP_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(model_setup, name)

    source = inspect.getsource(model_setup)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_model_setup_module_has_no_vertical_or_worker_filesystem_defaults() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(model_setup).lower()

    forbidden = {
        "quant",
        "trader",
        "finance",
        "platform-orchestrator",
        "ibkr",
        "pqrs",
        "pqrsd",
        "leila",
        "war room",
        "job hunter",
        "read_only=false",
        "duckdb.connect",
        "duckclaw.workers.factory",
        "duckclaw.workers.manifest",
        "duckclaw.workers.loader",
        "list_workers",
        "load_manifest",
        "load_system_prompt",
        "templates/workers",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_model_setup_llm_state_is_chat_scoped_runtime_setting() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    db = duckclaw.DuckClaw(":memory:")

    out = model_setup.execute_setup(db, "chat1", "provider=gemini | model=gemini-custom")
    current = model_setup.execute_model(db, "chat1", "")
    provider = resolve_runtime_setting(
        db,
        tenant_id="default",
        actor_email="chat:chat1",
        domain="runtime.session",
        key="llm_provider",
    )
    model = resolve_runtime_setting(
        db,
        tenant_id="default",
        actor_email="chat:chat1",
        domain="runtime.session",
        key="llm_model",
    )

    assert "Config actualizado" in out
    assert "provider: gemini" in current
    assert "model: gemini-custom" in current
    assert provider["source"] == "db"
    assert provider["value"] == "gemini"
    assert model["source"] == "db"
    assert model["value"] == "gemini-custom"


def test_model_setup_does_not_use_agent_config_for_llm_triplet() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(model_setup)

    forbidden = {
        'get_chat_state(db, chat_id, "llm_provider"',
        'get_chat_state(db, chat_id, "llm_model"',
        'get_chat_state(db, chat_id, "llm_base_url"',
        'set_chat_state(db, chat_id, "llm_provider"',
        'set_chat_state(db, chat_id, "llm_model"',
        'set_chat_state(db, chat_id, "llm_base_url"',
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_prompt_change_writes_system_prompt_policy_registry() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)
    db = duckclaw.DuckClaw(":memory:")

    out = model_setup.execute_prompt(db, "chat1", "default --change Eres policy DB-first.")
    current = model_setup.get_effective_system_prompt(db, "default")
    rows = db.execute(
        """
        SELECT content, active, status
        FROM main.prompt_policy_registry
        WHERE policy_type = 'system_prompt'
          AND policy_name = 'default'
          AND version = 1
        """
    )
    row = rows[0] if isinstance(rows, list) and rows else None

    assert "actualizado" in out
    assert current == "Eres policy DB-first."
    assert row == ("Eres policy DB-first.", True, "active")


def test_model_setup_does_not_use_agent_config_for_system_prompt() -> None:
    model_setup = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(model_setup)

    forbidden = {
        'f"system_prompt_{wid}"',
        'f"system_prompt_{worker_id}"',
        '_get_global_config(db, "system_prompt")',
        '_set_global_config(db, "system_prompt"',
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []

