from __future__ import annotations

from pathlib import Path


def test_projects_page_exposes_db_first_project_worker_assignment() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "Catálogo DB-first" in page
    assert "admin_project_agents" in page
    assert "Asignar agente" in page
    assert "removeWorkspaceProjectAgent" in page
    assert "listWorkspaceProjects" in service
    assert "assignWorkspaceProjectAgent" in service
