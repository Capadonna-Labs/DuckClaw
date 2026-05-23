"""Perfil Spawn: escrituras inline y hub RW en graph."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest


def test_spawn_profile_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

    from duckclaw.spawn_profile import is_spawn_profile, spawn_inline_writes_enabled

    assert is_spawn_profile() is False
    assert spawn_inline_writes_enabled() is False

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    assert is_spawn_profile() is True
    assert spawn_inline_writes_enabled() is True

    monkeypatch.setenv("DUCKCLAW_SPAWN_USE_DB_WRITER", "yes")
    assert spawn_inline_writes_enabled() is False


def test_skip_runtime_ddl_false_when_rw(tmp_path: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import _skip_runtime_ddl

    db_path = tmp_path / "hub.duckdb"
    with DuckClaw(str(db_path), read_only=False, engine="python") as db:
        assert getattr(db, "_read_only", True) is False
        assert _skip_runtime_ddl(db) is False


def test_enqueue_inline_applies_sql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    vault_dir = tmp_path / "db" / "private" / "default"
    vault_dir.mkdir(parents=True)
    db_path = vault_dir / "duckclaw.duckdb"
    duckdb.connect(str(db_path)).execute(
        "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT)"
    ).close()

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")

    from duckclaw.db_write_queue import apply_duckdb_write_sync, enqueue_duckdb_write_sync

    with patch("duckclaw.db_write_queue.spawn_inline_writes_enabled", return_value=True):
        tid = enqueue_duckdb_write_sync(
            db_path=str(db_path),
            query="INSERT INTO agent_config (key, value) VALUES (?, ?)",
            params=["k1", "v1"],
            user_id="default",
            tenant_id="default",
        )
        assert tid

        tid2 = apply_duckdb_write_sync(
            db_path=str(db_path),
            query="INSERT INTO agent_config (key, value) VALUES (?, ?)",
            params=["k2", "v2"],
        )
        assert tid2

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = {r[0]: r[1] for r in con.execute("SELECT key, value FROM agent_config").fetchall()}
        assert rows["k1"] == "v1"
        assert rows["k2"] == "v2"
    finally:
        con.close()
