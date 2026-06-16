from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

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


def test_crons_delta_with_read_only_handle_queues_typed_agent_config_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.commands.chat_state import _chat_key
    from duckclaw.db_write_queue import DbWriteTaskStatus

    crons = importlib.import_module(CANONICAL_MODULE)
    captured: list[Any] = []

    class ReadOnlyDb:
        _read_only = True

        def __init__(self, db_path: Path) -> None:
            self._path = str(db_path)
            self.released = 0
            self.resumed = 0
            self.direct_writes: list[str] = []

        def execute(self, sql: str) -> None:
            self.direct_writes.append(sql)
            raise AssertionError(f"read-only /crons must not execute SQL directly: {sql}")

        def query(self, _sql: str) -> list[dict[str, str]]:
            return []

        def release_file_handle_for_external_writer(self) -> None:
            self.released += 1

        def resume_readonly_file_handle(self) -> None:
            self.resumed += 1

    def fake_enqueue(command: Any, *, db_path: str, user_id: str) -> str:
        captured.append((command, db_path, user_id))
        return command.task_id

    monkeypatch.setattr(
        "harness_core.targets.load_homeostasis_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(goals=[]),
    )
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue)
    monkeypatch.setattr(
        "duckclaw.db_write_queue.poll_task_status_sync",
        lambda *_args, **_kwargs: DbWriteTaskStatus(status="success"),
    )

    db_path = tmp_path / "vault.duckdb"
    db = ReadOnlyDb(db_path)
    out = crons.execute_crons_schedule(db, "chat1", "--delta 1h", tenant_id="tenant-a")

    merged_entries: dict[str, str] = {}
    primary_db_path = str(db_path.resolve())
    primary_commands = 0
    for command, target_db_path, user_id in captured:
        assert command.command_type == "upsert_agent_config_entries"
        if target_db_path == primary_db_path:
            primary_commands += 1
            assert command.tenant_id == "tenant-a"
            assert command.actor_email == "chat:chat1"
            assert user_id == "chat1"
        merged_entries.update(command.entries)

    assert "Revisión proactiva cada" in out
    assert primary_commands >= 1
    assert merged_entries[_chat_key("chat1", "goals_delta_seconds")] == "3600"
    assert merged_entries[_chat_key("chat1", "goals_proactive_tenant_id")] == "tenant-a"
    assert merged_entries[_chat_key("chat1", "goals_cron_wall")] == ""
    assert db.direct_writes == []
    assert db.released >= 1
    assert db.resumed == db.released


def test_on_the_fly_crons_imports_remain_compatible() -> None:
    crons = importlib.import_module(CANONICAL_MODULE)

    for name in CRON_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(crons, name)
    for name in CRON_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(crons, name)
    assert crons.execute_goals is crons.execute_crons_schedule
