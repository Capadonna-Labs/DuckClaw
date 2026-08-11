from __future__ import annotations

from pathlib import Path


def test_mcp_android_preset_and_adb_ui_static() -> None:
    presets = Path("packages/shared/src/duckclaw/seeds/mcp_connector_presets.yaml").read_text(
        encoding="utf-8"
    )
    primary = Path("apps/duckclaw-admin/src/lib/mcpConnectorPrimaryAction.ts").read_text(encoding="utf-8")
    drawer = Path("apps/duckclaw-admin/src/components/mcp/ConnectorDetailDrawer.tsx").read_text(
        encoding="utf-8"
    )
    auth = Path("apps/duckclaw-admin/src/lib/mcpPresetAuth.ts").read_text(encoding="utf-8")

    assert "android:" in presets
    assert "auth_kind: adb" in presets
    assert "connection_type: adb_device" in presets
    assert "usesAdbDevice" in primary
    assert "connect_adb" in primary
    assert "presetUsesAdbDevice" in auth
    assert "ADB conectado" in drawer
    assert "Conectar ADB" in drawer
    assert "pm2_start_android_mcp" in drawer
