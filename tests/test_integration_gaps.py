"""Tests for duckclaw.integration_gaps."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.bootstrap_core import bootstrap_core_schema
from duckclaw.integration_gaps import (
    build_integration_secret_gaps,
    build_optional_integration_flags,
    integrations_for_skill,
)


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_integrations_for_skill_research_maps_tavily() -> None:
    entries = integrations_for_skill("research")
    assert any(entry.integration_id == "tavily" for entry in entries)


def test_build_integration_secret_gaps_openweather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    gaps = build_integration_secret_gaps(["openweather"])
    ow = [g for g in gaps if g["integration_id"] == "openweather"]
    assert len(ow) == 1
    assert ow[0]["skill"] == "openweather"
    assert "Integraciones" in ow[0]["message"]


def test_build_optional_integration_flags_with_env(
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        flags = build_optional_integration_flags(["research"], db=adapter, tenant_id="default")
        assert flags.get("tavily") is True
    finally:
        con.close()
