from __future__ import annotations

from pathlib import Path

from admin_service_corpus import admin_service_corpus


def test_telegram_page_uses_runtime_settings_not_env_editor() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/telegram/page.tsx").read_text(encoding="utf-8")
    view = Path(
        "apps/duckclaw-admin/src/components/integrations/TelegramIntegrationPageView.tsx"
    ).read_text(encoding="utf-8")
    editor = Path("apps/duckclaw-admin/src/components/telegram/TelegramWebhookRoutesEditor.tsx").read_text(
        encoding="utf-8"
    )
    service = admin_service_corpus()

    assert "redirect('/integraciones?tab=telegram')" in page
    assert "admin_runtime_settings" in view
    assert "telegram.webhook_routes" in view
    assert "getEnv" not in view
    assert "patchEnv" not in view
    assert "Guardar rutas en DuckDB" in editor
    assert "Guardar rutas en .env" not in editor
    assert "Runtime Settings DB-first" in editor
    assert "source?: string" in service
    assert "worker_id: string" in service
    assert "tenant_id: string" in service
