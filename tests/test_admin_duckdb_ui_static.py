from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_EXPLORER = ROOT / "apps/duckclaw-admin/src/components/duckdb/TableExplorer.tsx"
ADMIN_SERVICE = ROOT / "apps/duckclaw-admin/src/services/adminService.ts"


def test_duckdb_explorer_shows_authenticated_session_database_metadata() -> None:
    explorer = TABLE_EXPLORER.read_text(encoding="utf-8")
    service = ADMIN_SERVICE.read_text(encoding="utf-8")

    assert "vault_user_id" in service
    assert "table_count" in service
    assert "BD de sesión" in explorer
    assert "Usuario vault" in explorer
    assert "table_count" in explorer
    assert "setOpenSchemas(new Set(Object.keys(data.schemas || {})))" in explorer
