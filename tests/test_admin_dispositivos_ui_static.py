from __future__ import annotations

from pathlib import Path


def test_dispositivos_page_view_static() -> None:
    page = Path("apps/duckclaw-admin/src/components/integrations/DispositivosPageView.tsx").read_text(
        encoding="utf-8"
    )
    nav = Path("apps/duckclaw-admin/src/config/integracionesNav.ts").read_text(encoding="utf-8")
    hub = Path("apps/duckclaw-admin/src/app/(admin)/integraciones/page.tsx").read_text(encoding="utf-8")

    assert "DispositivosPageView" in hub
    assert "dispositivos" in nav
    assert "Dispositivos" in nav
    assert "/api/admin/devices/android-status" in page
    assert "DeviceStatusCard" in page
    assert "/mcp/connectors" in page
    assert "Dar grant" not in page
    assert "onGrant" not in page
    assert "streamlit" not in page.lower()
    assert "libedgecore" not in page.lower()
    assert "build_edge_native" not in page


def test_dispositivos_redirect_from_legacy_edge_path() -> None:
    redirect_page = Path(
        "apps/duckclaw-admin/src/app/(admin)/integrations/edge-devices/page.tsx"
    ).read_text(encoding="utf-8")
    assert "tab=dispositivos" in redirect_page
