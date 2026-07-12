"""Tests for github_token resolver."""

from __future__ import annotations

import duckdb
import pytest

from duckclaw.admin_runtime_settings import upsert_runtime_setting
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.bootstrap_core import bootstrap_core_schema
from duckclaw.github_token import github_token_configured, resolve_github_token


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_resolve_github_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test")
    assert resolve_github_token() == "ghp-test"
    assert github_token_configured()


def test_resolve_github_db_over_env(gateway_db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="gh@test.local")
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="",
            domain="integrations",
            key="github.token",
            value_text="db-token",
            secret=True,
            updated_by="gh@test.local",
        )
        resolved = resolve_github_token(db=adapter, tenant_id=profile["tenant_id"])
        assert resolved == "db-token"
    finally:
        con.close()
