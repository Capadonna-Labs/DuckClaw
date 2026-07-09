"""DEFAULT_SESSION_DB_RELPATH y alias get_session_db_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.gateway_db import (
    DEFAULT_SESSION_DB_RELPATH,
    get_gateway_db_path,
    get_session_db_path,
    raw_gateway_db_path_from_environ,
)


def test_default_session_db_relpath_value() -> None:
    assert DEFAULT_SESSION_DB_RELPATH == "db/private/default/duckclaw.duckdb"


def test_raw_gateway_db_path_fallback_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DUCKCLAW_GATEWAY_DB_PATH",
        "DUCKCLAW_TENANT_DB_PATH",
        "DUCKCLAW_VAULT_DB_PATH",
        "DUCKDB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    assert raw_gateway_db_path_from_environ() == DEFAULT_SESSION_DB_RELPATH


def test_get_session_db_path_is_alias_of_gateway_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    (repo / "db" / "private" / "default").mkdir(parents=True)
    db = repo / "db" / "private" / "default" / "duckclaw.duckdb"
    db.touch()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    for key in (
        "DUCKCLAW_GATEWAY_DB_PATH",
        "DUCKCLAW_TENANT_DB_PATH",
        "DUCKCLAW_VAULT_DB_PATH",
        "DUCKDB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    assert get_session_db_path() == get_gateway_db_path()
    assert Path(get_session_db_path()) == db.resolve()


def test_iter_goals_ticker_includes_split_hub_private_vaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Hub en db/duckclaw.duckdb debe escanear vaults en db/private/*/*.duckdb."""
    from duckclaw.gateway_db import iter_goals_ticker_duckdb_paths

    repo = tmp_path / "product"
    hub = repo / "db" / "duckclaw.duckdb"
    vault = repo / "db" / "private" / "admin-conv-abc" / "default.duckdb"
    hub.parent.mkdir(parents=True)
    vault.parent.mkdir(parents=True)
    hub.touch()
    vault.touch()
    monkeypatch.chdir(repo)
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(hub))
    monkeypatch.delenv("DUCKCLAW_GOALS_TICKER_DB_PATH", raising=False)
    paths = iter_goals_ticker_duckdb_paths()
    assert str(hub.resolve()) in paths
    assert str(vault.resolve()) in paths
