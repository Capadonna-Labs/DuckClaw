from __future__ import annotations

from pathlib import Path


def test_playground_ui_can_scope_chat_to_db_first_project() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useAdminChat.ts").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "Proyecto activo" in page
    assert "projectId" in page
    assert "selectableWorkers" in page
    assert "project_id: projectId || undefined" in hook
    assert "project_id?: string" in service
