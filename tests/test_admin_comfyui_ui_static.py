from __future__ import annotations

from pathlib import Path


def test_comfyui_page_exposes_runtime_settings_db_first() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/gen/image/page.tsx").read_text(
        encoding="utf-8"
    )
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    bff = Path("apps/duckclaw-admin/src/lib/comfyuiBff.ts").read_text(encoding="utf-8")

    assert "Configuración ComfyUI" in page
    assert "comfyui.api_url" in page
    assert "comfyui.timeout_sec" in page
    assert "patchRuntimeSettings" in page
    assert "Guardar en DuckDB" in page
    assert "source?: string" in service
    assert "timeout_sec?: string" in service
    assert "NEXT_PUBLIC_COMFYUI_API_URL" not in bff
