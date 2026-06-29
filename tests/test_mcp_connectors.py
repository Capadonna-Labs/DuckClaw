from __future__ import annotations

from pathlib import Path


def test_mcp_connectors_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    module = Path("services/api-gateway/routers/admin_domains/mcp_connectors.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.mcp_connectors import router as mcp_connectors_router" in admin
    assert "router.include_router(mcp_connectors_router)" in admin
    assert 'router = APIRouter(prefix="/mcp/connectors", tags=["admin-mcp-connectors"])' in module
    assert '@router.get("/presets", dependencies=[Depends(require_admin_key)])' in module
    assert '@router.post("/{connector_id}/test", dependencies=[Depends(require_admin_key)])' in module


def test_mcp_hub_links_connectors_page() -> None:
    hub = Path("apps/duckclaw-admin/src/app/(admin)/mcp/page.tsx").read_text(encoding="utf-8")
    page = Path("apps/duckclaw-admin/src/app/(admin)/mcp/connectors/page.tsx").read_text(encoding="utf-8")
    panel = Path("apps/duckclaw-admin/src/components/mcp/McpConnectorsPanel.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert 'href: "/mcp/connectors"' in hub
    assert "Conectores MCP" in page
    assert "McpConnectorsPanel" in page
    assert "listMcpConnectors" in panel
    assert "testMcpConnector" in service
    assert "grantMcpConnector" in service
    assert "createMcpConnector" in service
