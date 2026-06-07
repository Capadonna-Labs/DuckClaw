from __future__ import annotations

import re
from pathlib import Path


def test_projects_page_exposes_db_first_project_worker_assignment() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    table = Path("apps/duckclaw-admin/src/components/projects/ProjectsTable.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    workspace = Path("packages/shared/src/duckclaw/admin_workspace.py").read_text(encoding="utf-8")
    db_first_router = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")

    assert "Catálogo DB-first" in page
    assert "listWorkspaceProjectsPage" in page
    assert "page.projects.length === 0" in page
    assert "page.total > 0" in page
    assert "Math.floor((page.total - 1) / limit) * limit" in page
    assert "setOffset(maxOffset)" in page
    assert "ProjectsCatalogToolbar" in page
    assert "ProjectsTable" in page
    assert 'href="/projects/orchestrator"' in page
    assert "admin_project_agents" in workspace
    assert "Asignar agente" not in page
    assert "removeWorkspaceProjectAgent" not in page
    assert "deleteWorkspaceProject" in page
    assert "Eliminar definitivo" in table
    assert "deactivateWorkspaceProject" in page
    assert "reactivateWorkspaceProject" in page
    assert "status={status}" in page
    assert "onStatusChange" in page
    assert "confirm(" in page
    assert "listWorkspaceProjects" in service
    assert "assignWorkspaceProjectAgent" in service
    assert "deleteWorkspaceProject" in service
    assert "createOrchestratorDraft" in service
    assert "confirmOrchestratorDraft" in service
    assert "/workspace/orchestrator/draft" in service
    assert "createOrchestratorDraft" not in page
    assert "confirmOrchestratorDraft" not in page
    assert "orchestratorPrompt" not in page
    assert "textarea" not in page
    assert "worker=platform-orchestrator" in table
    assert "project=${encodeURIComponent(project.project_id)}" in table
    assert "Se eliminará definitivamente de la tabla de proyectos" in page
    assert '@router.post("/workspace/orchestrator/draft"' in db_first_router
    assert "workspace/orchestrator/" in bff_proxy
    assert "gateway_stale" in bff_proxy


def test_admin_service_exposes_paginated_workspace_projects_contract() -> None:
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "WorkspaceProjectsQuery" in service
    assert "WorkspaceProjectsPage" in service
    assert "listWorkspaceProjectsPage" in service
    assert "agents?:" in service
    assert "q:" in service
    assert "total: number;" in service
    assert "limit:" in service
    assert "limit: number;" in service
    assert "offset:" in service
    assert "offset: number;" in service
    assert "qs.set('q'" in service
    assert "qs.set('status'" in service
    assert "qs.set('limit'" in service
    assert "qs.set('offset'" in service
    assert "adminService.listWorkspaceProjectsPage" not in service
    assert re.search(
        r"listWorkspaceProjects:\s*\(\)\s*=>\s*listWorkspaceProjectsPage\(\)\.then\(\(r\)\s*=>\s*r\.projects\)",
        service,
    )


def test_projects_catalog_exposes_inactive_filter_and_reversible_actions() -> None:
    toolbar = Path("apps/duckclaw-admin/src/components/projects/ProjectsCatalogToolbar.tsx").read_text(encoding="utf-8")
    table = Path("apps/duckclaw-admin/src/components/projects/ProjectsTable.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "statusOptions" in toolbar
    assert "{ value: 'active', label: 'Activos' }" in toolbar
    assert "{ value: 'inactive', label: 'Inactivos' }" in toolbar
    assert "{ value: 'all', label: 'Todos' }" in toolbar
    assert "onStatusChange" in toolbar
    assert "onDeactivate" in table
    assert "onReactivate" in table
    assert "project.status === 'inactive'" in table
    assert "Activar" in table
    assert "Desactivar" in table
    assert "Eliminar definitivo" in table
    assert "deactivateWorkspaceProject:" in service
    assert "reactivateWorkspaceProject:" in service


def test_projects_catalog_and_orchestrator_wizard_are_separate_routes() -> None:
    projects_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    wizard_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/orchestrator/page.tsx").read_text(encoding="utf-8")
    wizard_component = Path(
        "apps/duckclaw-admin/src/components/projects/ProjectOrchestratorWizard.tsx"
    ).read_text(encoding="utf-8")

    assert 'href="/projects/orchestrator"' in projects_page
    assert "listWorkspaceProjectsPage" in projects_page
    assert "ProjectsCatalogToolbar" in projects_page
    assert "ProjectsTable" in projects_page
    assert "createOrchestratorDraft" not in projects_page
    assert "confirmOrchestratorDraft" not in projects_page
    assert "orchestratorPrompt" not in projects_page
    assert "ProjectOrchestratorWizard" in wizard_page
    assert "createOrchestratorDraft" in wizard_component
    assert "confirmOrchestratorDraft" in wizard_component
    assert "questionAnswers" in wizard_component
    assert "Análisis del Orchestrator" in wizard_component
    assert "htmlFor={answerId}" in wizard_component
    assert "orchestrator-question-${index}" in wizard_component
    assert "Respuesta opcional" in wizard_component
    assert "Continuar sin responder" in wizard_component
    assert "Para incorporarlas al borrador, ajusta el objetivo" in wizard_component


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
