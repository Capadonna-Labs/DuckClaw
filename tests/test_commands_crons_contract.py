from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.crons"
CRON_FUNCTION_EXPORTS = (
    "_crons_debug_log",
    "_normalize_cron_rm_id",
    "_extract_crons_delta_options",
    "parse_goals_delta_arg",
    "format_goals_delta_interval_human",
    "format_goals_countdown_human",
    "_goals_proactive_interval_countdown_parts",
    "format_platform_cron_summary",
    "_short_session_uid_for_crons",
    "_crons_goals_delta_meta_dict",
    "_crons_goals_delta_listing_section",
    "chat_id_from_goals_delta_config_key",
    "chat_id_from_goals_cron_wall_key",
    "_apply_interval_only_clear",
    "clear_interval_schedule_only",
    "_goals_cron_wall_listing_note",
    "clear_goals_cron_wall_storage",
    "clear_goals_proactive_schedule",
    "build_goals_proactive_system_event_message",
    "execute_crons_schedule",
    "execute_goals",
)
CRON_CONSTANT_EXPORTS = (
    "_GOALS_DELTA_SECONDS_KEY",
    "_GOALS_PROACTIVE_LAST_FIRE_KEY",
    "_GOALS_PROACTIVE_ANCHOR_KEY",
    "_GOALS_PROACTIVE_TENANT_KEY",
    "_GOALS_DELTA_ANCHOR_LEGACY_KEY",
    "_GOALS_DELTA_META_KEY",
    "_GOALS_PROACTIVE_NOTIFY_KEY",
    "_GOALS_CRON_WALL_KEY",
    "GOALS_DELTA_MIN_SECONDS",
    "GOALS_DELTA_MAX_SECONDS",
    "CRON_SCHEDULE_ID_DELTA",
    "CRON_SCHEDULE_ID_WALL",
)


def test_crons_command_ownership_lives_outside_graphs() -> None:
    crons = importlib.import_module(CANONICAL_MODULE)

    for name in CRON_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(crons)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_crons_remote_schedule_clears_use_typed_db_writer_only() -> None:
    crons = importlib.import_module(CANONICAL_MODULE)

    source = inspect.getsource(crons)

    assert "read_only=False" not in source
    assert "enqueue_duckdb_write_sync" not in source
    assert "UpsertAgentConfigEntriesCommand" in source
    assert "enqueue_typed_command" in source


def test_on_the_fly_crons_imports_remain_compatible() -> None:
    crons = importlib.import_module(CANONICAL_MODULE)

    for name in CRON_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(crons, name)
    for name in CRON_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(crons, name)
    assert crons.execute_goals is crons.execute_crons_schedule
