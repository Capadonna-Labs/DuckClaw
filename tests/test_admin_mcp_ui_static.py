from __future__ import annotations

from pathlib import Path


def test_mcp_page_exposes_runtime_settings_port_db_first() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/mcp/config/page.tsx").read_text(encoding="utf-8")
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


def test_mcp_page_separates_runtime_tools_reference_and_stdio_sections() -> None:
    hub = Path("apps/duckclaw-admin/src/app/(admin)/mcp/page.tsx").read_text(encoding="utf-8")
    runtime = Path("apps/duckclaw-admin/src/app/(admin)/mcp/runtime/page.tsx").read_text(encoding="utf-8")
    config = Path("apps/duckclaw-admin/src/app/(admin)/mcp/config/page.tsx").read_text(encoding="utf-8")
    server = Path("apps/duckclaw-admin/src/app/(admin)/mcp/server/page.tsx").read_text(encoding="utf-8")
    tools = Path("apps/duckclaw-admin/src/app/(admin)/mcp/tools/page.tsx").read_text(encoding="utf-8")
    catalog = Path("apps/duckclaw-admin/src/app/(admin)/mcp/catalog/page.tsx").read_text(encoding="utf-8")

    assert 'href: "/mcp/runtime"' in hub
    assert 'href: "/mcp/config"' in hub
    assert 'href: "/mcp/server"' in hub
    assert 'href: "/mcp/tools"' in hub
    assert 'href: "/mcp/catalog"' in hub
    assert "Estado runtime MCP" in runtime
    assert "Configuración MCP" in config
    assert "Servidor DuckClaw MCP" in server
    assert "Herramientas DuckClaw MCP" in tools
    assert "Catálogo oficial MCP" in catalog
    assert "OfficialMcpReferenceTable" in catalog
    assert "data.official_reference.servers" in catalog
    assert "OfficialMcpReferenceTable" not in hub
    assert "patchRuntimeSettings" not in hub
