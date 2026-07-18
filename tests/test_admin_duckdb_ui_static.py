from __future__ import annotations

from pathlib import Path

from admin_service_corpus import admin_service_corpus


ROOT = Path(__file__).resolve().parents[1]
TABLE_EXPLORER = ROOT / "apps/duckclaw-admin/src/components/duckdb/TableExplorer.tsx"


def test_duckdb_explorer_shows_authenticated_session_database_metadata() -> None:
    explorer = TABLE_EXPLORER.read_text(encoding="utf-8")
    service = admin_service_corpus()

    assert "vault_user_id" in service
    assert "table_count" in service
    assert "Usuario vault" in explorer
    assert "table_count" in explorer
    assert "setOpenSchemas(new Set(Object.keys(data.schemas || {})))" in explorer
