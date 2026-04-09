"""resolve_env_duckdb_path: rutas relativas ancladas al repo (PM2 cwd-safe)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.gateway_db import ensure_usable_duckdb_file, get_gateway_db_path, resolve_env_duckdb_path


def test_relative_path_joins_duckclaw_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "myrepo"
    (repo / "db" / "nested").mkdir(parents=True)
    expected = repo / "db" / "nested" / "vault.duckdb"
    expected.touch()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    out = resolve_env_duckdb_path("db/nested/vault.duckdb")
    assert Path(out) == expected.resolve()


def test_get_gateway_db_falls_back_to_finanz_when_no_duckclaw_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "r"
    (repo / "db").mkdir(parents=True)
    f = repo / "db" / "f.duckdb"
    f.touch()
    monkeypatch.delenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_JOB_HUNTER_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_SIATA_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", "db/f.duckdb")
    assert Path(get_gateway_db_path()) == f.resolve()


def test_ensure_usable_duckdb_file_removes_zero_byte_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "stub.duckdb"
    p.write_bytes(b"")
    assert p.stat().st_size == 0
    ensure_usable_duckdb_file(str(p))
    assert not p.exists()


def test_absolute_path_unchanged_modulo_resolve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    f = tmp_path / "a.duckdb"
    f.touch()
    p = str(f.resolve())
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", "/nope")
    assert resolve_env_duckdb_path(p) == p
