from __future__ import annotations

import importlib

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.loop"
# on_the_fly re-exports a mixed loop/meditate alias surface during the rename.
ON_THE_FLY_LOOP_EXPORTS = (
    "parse_loop_delta_arg",
    "chat_id_from_loop_delta_config_key",
    "clear_loop_schedule",
    "get_loop_schedule_status",
    "apply_loop_schedule",
    "_format_meditate_cycle_summary",
    "_publish_loop_tick_heartbeat",
    "_resolve_loop_vault_user_id",
    "invoke_loop_cycle_for_chat",
    "execute_meditate",
)
LEGACY_MEDITATE_EXPORTS = (
    "parse_meditate_delta_arg",
    "execute_meditate",
    "get_meditate_schedule_status",
)


def test_loop_command_ownership_lives_outside_graphs() -> None:
    loop = importlib.import_module(CANONICAL_MODULE)

    for name in ON_THE_FLY_LOOP_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE, name

    # Ownership: execute_loop is defined in commands.loop (graphs only re-exports).
    assert loop.execute_loop.__module__ == CANONICAL_MODULE
    assert loop.parse_loop_delta_arg.__module__ == CANONICAL_MODULE


def test_on_the_fly_loop_imports_remain_compatible() -> None:
    loop = importlib.import_module(CANONICAL_MODULE)

    assert on_the_fly_commands.parse_loop_delta_arg is loop.parse_loop_delta_arg
    assert on_the_fly_commands.execute_meditate is loop.execute_loop
    assert on_the_fly_commands._format_meditate_cycle_summary is loop._format_loop_cycle_summary
    assert on_the_fly_commands.clear_loop_schedule is loop.clear_loop_schedule
    assert on_the_fly_commands.get_loop_schedule_status is loop.get_loop_schedule_status

    for name in LEGACY_MEDITATE_EXPORTS:
        assert hasattr(loop, name)


def test_meditate_shim_reexports_loop() -> None:
    meditate = importlib.import_module("duckclaw.commands.meditate")
    loop = importlib.import_module("duckclaw.commands.loop")
    assert meditate.execute_meditate is loop.execute_loop
    assert meditate.parse_meditate_delta_arg is loop.parse_loop_delta_arg
