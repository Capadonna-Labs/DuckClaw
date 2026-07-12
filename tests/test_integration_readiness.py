"""Tests for integration_readiness sensor lines."""

from __future__ import annotations

import duckdb

from duckclaw.commands.sensors import execute_sensors
from duckclaw.integration_readiness import integration_catalog_sensor_lines


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def query(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params).fetchall()
        return self._con.execute(sql).fetchall()


def test_integration_catalog_sensor_lines_lists_pack(gateway_db) -> None:
    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        lines = integration_catalog_sensor_lines(con)
    finally:
        con.close()
    text = "\n".join(lines)
    assert "Tavily" in text
    assert "Integraciones" in text


def test_execute_sensors_mentions_integraciones_block(gateway_db, monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        adapter = _Adapter(con)
        out = execute_sensors(adapter)
    finally:
        con.close()
    assert "Integraciones (API keys)" in out
    assert "Tavily" in out
