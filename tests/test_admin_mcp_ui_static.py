from __future__ import annotations

from pathlib import Path


def test_mcp_page_exposes_runtime_settings_port_db_first() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/mcp/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    status_route = Path("apps/duckclaw-admin/src/app/api/admin/mcp-status/route.ts").read_text(
        encoding="utf-8"
    )

    assert "Configuración MCP" in page
    assert "mcp.port" in page
    assert "patchRuntimeSettings" in page
    assert "Guardar en DuckDB" in page
    assert "Fuente efectiva" in page
    assert "port?: string" in service
    assert "source?: string" in service
    assert "/api/v1/admin/catalog/mcp" in status_route
    assert "gatewayBase()" in status_route
