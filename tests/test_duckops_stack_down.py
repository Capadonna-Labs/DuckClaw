"""Tests for duckops stack shutdown helpers."""

from __future__ import annotations

from pathlib import Path

from duckops.stack_shutdown import CORE_PM2_NAMES, duckdb_paths_to_unlock


def test_core_pm2_names_include_gateway_and_writer() -> None:
    assert "DuckClaw-Gateway" in CORE_PM2_NAMES
    assert "DuckClaw-DB-Writer" in CORE_PM2_NAMES


def test_duckdb_paths_includes_private_axis_glob(tmp_path: Path) -> None:
    vault = tmp_path / "db" / "private" / "7822026745"
    vault.mkdir(parents=True)
    axis = vault / "duckclaw.duckdb"
    axis.write_text("stub", encoding="utf-8")
    paths = duckdb_paths_to_unlock(tmp_path)
    assert axis.resolve() in [p.resolve() for p in paths]
