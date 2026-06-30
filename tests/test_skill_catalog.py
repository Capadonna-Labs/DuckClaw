"""Tests for DB-first skill category catalog."""

from __future__ import annotations

import duckdb
import pytest


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_seed_framework_skill_catalog_is_idempotent(gateway_db) -> None:
    from duckclaw.skill_catalog import (
        list_skill_categories_from_db,
        seed_framework_skill_catalog_if_empty,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        first = seed_framework_skill_catalog_if_empty(adapter)
        second = seed_framework_skill_catalog_if_empty(adapter)
        categories = list_skill_categories_from_db(adapter)
    finally:
        con.close()

    assert first >= 0
    assert second == 0
    assert len(categories) >= 4
    ids = {cat["id"] for cat in categories}
    assert "web" in ids
    assert "reports_html" in ids
    assert "data_market" not in ids
    assert "ibkr" not in ids
    web = next(cat for cat in categories if cat["id"] == "web")
    skill_ids = {item["id"] for item in web["skills"]}
    assert "research" in skill_ids
    assert "google_trends" in skill_ids


def test_skill_categories_api_payload_includes_baseline_profiles(gateway_db) -> None:
    from duckclaw.skill_catalog import skill_categories_api_payload

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        payload = skill_categories_api_payload(adapter)
    finally:
        con.close()

    assert payload["pack_version"] == "framework_skill_categories_v1"
    assert isinstance(payload["categories"], list)
    assert "general" in payload["baseline_profiles"]
    assert "read_sql" in payload["baseline_profiles"]["general"]
