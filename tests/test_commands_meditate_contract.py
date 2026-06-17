from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.meditate"
MEDITATE_FUNCTION_EXPORTS = (
    "parse_meditate_delta_arg",
    "chat_id_from_meditate_delta_config_key",
    "clear_meditate_schedule",
    "get_meditate_schedule_status",
    "apply_meditate_schedule",
    "_format_meditate_cycle_summary",
    "_publish_meditate_tick_heartbeat",
    "_resolve_meditate_vault_user_id",
    "invoke_meditate_cycle_for_chat",
    "execute_meditate",
)
MEDITATE_CONSTANT_EXPORTS = (
    "_MEDITATE_DELTA_SECONDS_KEY",
    "_MEDITATE_LAST_FIRE_KEY",
    "_MEDITATE_TENANT_KEY",
    "_MEDITATE_WORKER_KEY",
    "MEDITATE_DELTA_MIN_SECONDS",
    "MEDITATE_DELTA_MAX_SECONDS",
)


def test_meditate_command_ownership_lives_outside_graphs() -> None:
    meditate = importlib.import_module(CANONICAL_MODULE)

    for name in MEDITATE_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(meditate)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_meditate_imports_remain_compatible() -> None:
    meditate = importlib.import_module(CANONICAL_MODULE)

    for name in MEDITATE_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(meditate, name)
    for name in MEDITATE_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(meditate, name)
