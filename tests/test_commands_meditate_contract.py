from __future__ import annotations

import importlib

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.loop"
# Meditate is a deprecated shim over loop; on_the_fly still re-exports meditate aliases.
ON_THE_FLY_MEDITATE_ALIASES = (
    "parse_loop_delta_arg",
    "chat_id_from_meditate_delta_config_key",
    "clear_loop_schedule",
    "get_loop_schedule_status",
    "apply_loop_schedule",
    "_format_meditate_cycle_summary",
    "_publish_loop_tick_heartbeat",
    "_resolve_meditate_vault_user_id",
    "invoke_loop_cycle_for_chat",
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
    meditate = importlib.import_module("duckclaw.commands.meditate")
    loop = importlib.import_module(CANONICAL_MODULE)

    assert meditate.execute_meditate is loop.execute_loop
    assert meditate.parse_meditate_delta_arg is loop.parse_loop_delta_arg

    for name in ON_THE_FLY_MEDITATE_ALIASES:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE, name


def test_on_the_fly_meditate_imports_remain_compatible() -> None:
    meditate = importlib.import_module("duckclaw.commands.meditate")
    loop = importlib.import_module(CANONICAL_MODULE)

    assert getattr(on_the_fly_commands, "execute_meditate") is loop.execute_loop
    assert getattr(on_the_fly_commands, "parse_loop_delta_arg") is loop.parse_loop_delta_arg
    for name in MEDITATE_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(loop, name)
    # meditate shim is `import *` (public names); underscore aliases live on loop / on_the_fly.
    assert meditate.execute_meditate is loop.execute_loop
    assert meditate.MEDITATE_DELTA_MIN_SECONDS == loop.MEDITATE_DELTA_MIN_SECONDS
    assert meditate.MEDITATE_DELTA_MAX_SECONDS == loop.MEDITATE_DELTA_MAX_SECONDS
