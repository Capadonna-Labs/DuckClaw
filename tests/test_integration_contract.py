"""Contract tests: integration pack ↔ fallbacks ↔ readiness."""

from __future__ import annotations

from duckclaw.integration_catalog import (
    integration_setting_fallbacks,
    list_integration_catalog_entries,
)
from duckclaw.integration_readiness import build_integration_readiness, missing_integration_labels


def test_pack_entries_have_runtime_setting_fallbacks() -> None:
    fallbacks = integration_setting_fallbacks()
    for entry in list_integration_catalog_entries():
        key = (entry.domain, entry.setting_key)
        assert key in fallbacks, f"missing fallback for {entry.integration_id}"
        assert fallbacks[key]["secret"] is True
        if entry.env_keys:
            assert fallbacks[key]["env_key"] in entry.env_keys


def test_readiness_covers_all_catalog_entries(gateway_db) -> None:
    import duckdb

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        rows = build_integration_readiness(con)
    finally:
        con.close()
    catalog_ids = {e.integration_id for e in list_integration_catalog_entries()}
    readiness_ids = {row.integration_id for row in rows}
    assert readiness_ids == catalog_ids


def test_missing_integration_labels_matches_unconfigured(gateway_db, monkeypatch) -> None:
    import duckdb

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        missing = missing_integration_labels(con)
        assert missing
        assert any("Tavily" in label for label in missing)
    finally:
        con.close()
