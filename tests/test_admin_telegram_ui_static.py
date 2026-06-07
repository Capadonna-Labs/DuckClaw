from __future__ import annotations

from pathlib import Path


def test_telegram_page_uses_runtime_settings_not_env_editor() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/telegram/page.tsx").read_text(encoding="utf-8")
    editor = Path("apps/duckclaw-admin/src/components/telegram/TelegramWebhookRoutesEditor.tsx").read_text(
        encoding="utf-8"
    )
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "admin_runtime_settings" in page
    assert "telegram.webhook_routes" in page
    assert "getEnv" not in page
    assert "patchEnv" not in page
    assert "Guardar rutas en DuckDB" in editor
    assert "Guardar rutas en .env" not in editor
    assert "Runtime Settings DB-first" in editor
    assert "source?: string" in service
    assert "worker_id: string" in service
    assert "tenant_id: string" in service
