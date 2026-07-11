from __future__ import annotations

from pathlib import Path


def test_edge_devices_page_wires_ops_buttons() -> None:
    page = Path("apps/duckclaw-admin/src/components/integrations/EdgeDevicesPageView.tsx").read_text(
        encoding="utf-8"
    )
    local_ops = Path("apps/duckclaw-admin/src/lib/localOps.ts").read_text(encoding="utf-8")

    assert "runOps" in page
    assert "build_edge_native" in page
    assert "pm2_start_edge_streamlit" in page
    assert "build_edge_native" in local_ops
    assert "ecosystem.edge-devices.config.cjs" in local_ops
