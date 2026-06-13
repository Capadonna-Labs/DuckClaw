"""resolve_env_duckdb_path: rutas relativas ancladas al repo (PM2 cwd-safe)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.gateway_db import (
    GATEWAY_DB_ENV_KEYS,
    get_gateway_db_path,
    raw_gateway_db_path_from_mapping,
    resolve_env_duckdb_path,
)


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


def test_get_gateway_db_uses_generic_gateway_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "r"
    (repo / "db").mkdir(parents=True)
    f = repo / "db" / "f.duckdb"
    f.touch()
    monkeypatch.delenv("DUCKCLAW_TENANT_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_VAULT_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "db/f.duckdb")
    assert Path(get_gateway_db_path()) == f.resolve()


def test_gateway_db_env_keys_include_generic_paths_before_duckdb_fallback() -> None:
    keys = list(GATEWAY_DB_ENV_KEYS)
    assert keys.index("DUCKCLAW_GATEWAY_DB_PATH") < keys.index("DUCKDB_PATH")
    assert keys.index("DUCKCLAW_TENANT_DB_PATH") < keys.index("DUCKDB_PATH")
    assert keys.index("DUCKCLAW_VAULT_DB_PATH") < keys.index("DUCKDB_PATH")


def test_raw_mapping_prefers_gateway_path_over_duckdb_path() -> None:
    m = {
        "DUCKDB_PATH": "/tmp/hub.duckdb",
        "DUCKCLAW_GATEWAY_DB_PATH": "/tmp/gateway.duckdb",
    }
    assert raw_gateway_db_path_from_mapping(m) == "/tmp/gateway.duckdb"


def test_absolute_path_unchanged_modulo_resolve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    f = tmp_path / "a.duckdb"
    f.touch()
    p = str(f.resolve())
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", "/nope")
    assert resolve_env_duckdb_path(p) == p
