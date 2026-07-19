from __future__ import annotations

from pathlib import Path

from admin_service_corpus import admin_service_corpus


def test_mcp_unified_view_has_connectors_server_and_reference_tabs() -> None:
    tabs = Path("apps/duckclaw-admin/src/components/mcp/mcpPageTabs.ts").read_text(encoding="utf-8")
    view = Path("apps/duckclaw-admin/src/components/mcp/McpUnifiedView.tsx").read_text(encoding="utf-8")
    connectors = Path("apps/duckclaw-admin/src/components/mcp/McpConnectorsPanel.tsx").read_text(
        encoding="utf-8"
    )
    config = Path("apps/duckclaw-admin/src/components/mcp/McpConfigurationPanel.tsx").read_text(
        encoding="utf-8"
    )
    service = admin_service_corpus()
    status_route = Path("apps/duckclaw-admin/src/app/api/admin/mcp-status/route.ts").read_text(
        encoding="utf-8"
    )

    assert "label: 'Conectores'" in tabs
    assert "label: 'Servidor'" in tabs
    assert "label: 'Referencia'" in tabs
    assert "McpConnectorsPanel" in view
    assert "McpConfigurationPanel" in view
    assert "OfficialMcpReferenceTable" in view
    assert "Referencia oficial MCP" in view
    assert "McpNewConnectorSection" in connectors
    assert "Nuevo desde plantilla" in connectors
    assert "ConnectorListRow" in connectors
    assert "ConnectorDetailDrawer" in connectors
    assert "data-mcp-connector-list" in connectors
    assert "AdminSideDrawer" in Path(
        "apps/duckclaw-admin/src/components/shared/AdminSideDrawer.tsx"
    ).read_text(encoding="utf-8")
    assert "resolveMcpConnectorPrimaryAction" in Path(
        "apps/duckclaw-admin/src/lib/mcpConnectorPrimaryAction.ts"
    ).read_text(encoding="utf-8")
    assert "McpNewConnectorSection" not in config
    assert "patchRuntimeSettings" in view
    assert "mcp.port" in config or "mcpPort" in config
    assert "port?: string" in service
    assert "source?: string" in service
    assert "/api/v1/admin/catalog/mcp" in status_route


def test_mcp_legacy_routes_redirect_to_unified_tabs() -> None:
    catalog = Path("apps/duckclaw-admin/src/app/(admin)/mcp/catalog/page.tsx").read_text(encoding="utf-8")
    config = Path("apps/duckclaw-admin/src/app/(admin)/mcp/config/page.tsx").read_text(encoding="utf-8")
    assert "redirect('/mcp?tab=catalog')" in catalog
    assert "redirect('/mcp?tab=config')" in config


def test_mcp_new_connector_selector_groups_by_product() -> None:
    section = Path(
        "apps/duckclaw-admin/src/components/mcp/McpNewConnectorSection.tsx"
    ).read_text(encoding="utf-8")
    auth = Path("apps/duckclaw-admin/src/lib/mcpPresetAuth.ts").read_text(encoding="utf-8")
    combobox = Path(
        "apps/duckclaw-admin/src/components/shared/SearchableGroupedSelect.tsx"
    ).read_text(encoding="utf-8")
    assert "SearchableGroupedSelect" in section
    assert "groupMcpPresetsForSelect" in section
    assert "existingConnectors" in section
    assert "(ya creado)" in section
    assert "filterMcpPresets" in auth
    assert "max-h-72" in combobox or 'data-virtualized="true"' in combobox or "data-virtualized" in combobox
    assert "VIEWPORT_H" in combobox or "virtualizado" in combobox or "translateY" in combobox
    assert "Buscar" in combobox or "searchPlaceholder" in combobox
    assert "preset.metadata?.admin_label" not in auth
    assert "preset.display_name" in auth
