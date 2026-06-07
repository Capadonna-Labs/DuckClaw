from __future__ import annotations

import re
from pathlib import Path


def test_projects_page_exposes_db_first_project_worker_assignment() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    workspace = Path("packages/shared/src/duckclaw/admin_workspace.py").read_text(encoding="utf-8")
    db_first_router = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")

    assert "Catálogo DB-first" in page
    assert "admin_project_agents" in workspace
    assert "Asignar agente" in page
    assert "removeWorkspaceProjectAgent" in page
    assert "deleteWorkspaceProject" in page
    assert "Eliminar proyecto" in page
    assert "confirm(" in page
    assert "listWorkspaceProjects" in service
    assert "assignWorkspaceProjectAgent" in service
    assert "deleteWorkspaceProject" in service
    assert "Platform Orchestrator" in page
    assert "createOrchestratorDraft" in service
    assert "confirmOrchestratorDraft" in service
    assert "/workspace/orchestrator/draft" in service
    assert '@router.post("/workspace/orchestrator/draft"' in db_first_router
    assert "workspace/orchestrator/" in bff_proxy
    assert "gateway_stale" in bff_proxy


def test_legacy_forge_projects_are_not_operational_in_admin_ui() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    projects_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    overview_page = Path("apps/duckclaw-admin/src/app/(admin)/overview/page.tsx").read_text(encoding="utf-8")
    templates_page = Path("apps/duckclaw-admin/src/app/(admin)/templates/page.tsx").read_text(encoding="utf-8")
    kanban_page = Path("apps/duckclaw-admin/src/app/(admin)/kanban/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    forge_route = Path("apps/duckclaw-admin/src/app/api/admin/forge-projects/route.ts").read_text(encoding="utf-8")
    forge_slug_route = Path("apps/duckclaw-admin/src/app/api/admin/forge-projects/[slug]/route.ts").read_text(encoding="utf-8")
    forge_apply_route = Path(
        "apps/duckclaw-admin/src/app/api/admin/forge-projects/[slug]/apply-team/route.ts"
    ).read_text(encoding="utf-8")
    forge_presets_route = Path(
        "apps/duckclaw-admin/src/app/api/admin/forge-projects/env-presets/route.ts"
    ).read_text(encoding="utf-8")

    combined_ui = "\n".join([nav, projects_page, overview_page, templates_page, kanban_page])
    assert 'href="/projects/new"' not in combined_ui
    assert "createForgeProject" not in service
    assert "listForgeProjects" not in service
    assert "applyForgeProjectTeam" not in service
    assert "listEnvForgeProjectPresets" not in service
    assert "createForgeProjectLocal" not in forge_route
    assert "listForgeProjectsLocal" not in forge_route
    assert "deleteForgeProjectLocal" not in forge_slug_route
    assert "loadEnvForgePresets" not in forge_presets_route
    for route in (forge_route, forge_slug_route, forge_apply_route, forge_presets_route):
        assert "410" in route
        assert "DB-first" in route


def test_sidebar_project_icon_is_imported() -> None:
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
    lucide_import = re.search(r"import \{\n(?P<body>.*?)\n\} from 'lucide-react';", sidebar, re.S)

    assert "'/projects': FolderPlus" in sidebar
    assert lucide_import is not None
    assert "FolderPlus" in lucide_import.group("body")
