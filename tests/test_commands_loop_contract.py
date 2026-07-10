from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.loop"
LOOP_FUNCTION_EXPORTS = (
    "parse_loop_delta_arg",
    "chat_id_from_loop_delta_config_key",
    "clear_loop_schedule",
    "get_loop_schedule_status",
    "apply_loop_schedule",
    "_format_loop_cycle_summary",
    "_publish_loop_tick_heartbeat",
    "_resolve_loop_vault_user_id",
    "invoke_loop_cycle_for_chat",
    "execute_loop",
)
LOOP_CONSTANT_EXPORTS = (
    "_LOOP_DELTA_SECONDS_KEY",
    "_LOOP_LAST_FIRE_KEY",
    "_LOOP_TENANT_KEY",
    "_LOOP_WORKER_KEY",
    "LOOP_DELTA_MIN_SECONDS",
    "LOOP_DELTA_MAX_SECONDS",
)
LEGACY_MEDITATE_EXPORTS = (
    "parse_meditate_delta_arg",
    "execute_meditate",
    "get_meditate_schedule_status",
)


def test_loop_command_ownership_lives_outside_graphs() -> None:
    loop = importlib.import_module(CANONICAL_MODULE)

    for name in LOOP_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name, None) or getattr(
            on_the_fly_commands, name.replace("loop", "meditate", 1), None
        )
        assert exported is not None, name
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(loop)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_loop_imports_remain_compatible() -> None:
    loop = importlib.import_module(CANONICAL_MODULE)

    for name in LOOP_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name, None)
        if exported is None and name.startswith("parse_loop"):
            exported = getattr(on_the_fly_commands, "parse_loop_delta_arg")
        assert getattr(loop, name) is exported or getattr(loop, name.replace("_loop", "_meditate")) is exported

    for name in LEGACY_MEDITATE_EXPORTS:
        assert hasattr(loop, name)


def test_meditate_shim_reexports_loop() -> None:
    meditate = importlib.import_module("duckclaw.commands.meditate")
    loop = importlib.import_module("duckclaw.commands.loop")
    assert meditate.execute_meditate is loop.execute_loop
    assert meditate.parse_meditate_delta_arg is loop.parse_loop_delta_arg
