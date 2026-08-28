"""Tests for duckclaw.integration_secrets."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.admin_runtime_settings import resolve_runtime_setting, upsert_runtime_setting
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.bootstrap_core import bootstrap_core_schema
from duckclaw.integration_secrets import (
    integration_api_key_configured,
    resolve_integration_api_key,
)


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_integration_spec_for_setting_key() -> None:
    from duckclaw.integration_catalog import integration_entry_for_setting_key

    spec = integration_entry_for_setting_key("tavily.api_key")
    assert spec is not None
    assert spec.integration_id == "tavily"


def test_resolve_tavily_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert resolve_integration_api_key("tavily") == "tvly-test"
    assert integration_api_key_configured("tavily")


def test_resolve_tavily_db_over_env(gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "env-key")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="alice@test.local")
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="",
            domain="integrations",
            key="tavily.api_key",
            value_text="db-key",
            secret=True,
            updated_by="alice@test.local",
        )
        resolved = resolve_integration_api_key(
            "tavily",
            db=adapter,
            tenant_id=profile["tenant_id"],
        )
        assert resolved == "db-key"
    finally:
        con.close()


def test_resolve_workspace_key_when_caller_tenant_default(
    gateway_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI guarda en tenant workspace; /loop a menudo invoca con tenant=default."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-stale")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="or-ws@test.local")
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="",
            domain="integrations",
            key="openrouter.api_key",
            value_text="sk-or-workspace-good",
            secret=True,
            updated_by="or-ws@test.local",
        )
        assert (
            resolve_integration_api_key(
                "openrouter",
                db=adapter,
                tenant_id="default",
                actor_email="or-ws@test.local",
            )
            == "sk-or-workspace-good"
        )
    finally:
        con.close()


def test_runtime_setting_lists_integrations_configured_from_env(
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAL_API_KEY", "fal-from-env")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="bob@test.local")
        row = resolve_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            domain="integrations",
            key="fal.api_key",
        )
        assert row["configured"] is True
        assert row["source"] == "env"
        assert row["secret"] is True
        assert "value_text" not in row
    finally:
        con.close()
