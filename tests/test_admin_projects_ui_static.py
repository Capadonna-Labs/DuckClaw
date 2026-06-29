from __future__ import annotations

import re
from pathlib import Path


def test_projects_page_exposes_db_first_project_worker_assignment() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    table = Path("apps/duckclaw-admin/src/components/projects/ProjectsTable.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    workspace = Path("packages/shared/src/duckclaw/admin_workspace.py").read_text(encoding="utf-8")
    db_first_router = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    workspace_router = Path(
        "services/api-gateway/routers/admin_domains/workspace_projects.py"
    ).read_text(encoding="utf-8")
    managed_draft_router = Path(
        "services/api-gateway/routers/admin_domains/workspace_managed_draft.py"
    ).read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")

    assert "<FolderKanban size={28} /> Proyectos" in page
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
    assert "ConfirmDangerModal" in page
    assert "pendingDeleteProject" in page
    assert "confirmDeleteProject" in page
    assert "Sí, eliminar proyecto" in page
    assert "deactivateWorkspaceProject" in page
    assert "reactivateWorkspaceProject" in page
    assert "status={status}" in page
    assert "onStatusChange" in page
    assert "confirm(" in page
    assert "listWorkspaceProjects" in service
    assert "assignWorkspaceProjectAgent" in service
    assert "deleteWorkspaceProject" in service
    assert "createManagedWorkspaceDraft" in service
    assert "confirmManagedWorkspaceDraft" in service
    assert "/workspace/orchestrator/draft" in service
    assert "createOrchestratorDraft" not in page
    assert "confirmOrchestratorDraft" not in page
    assert "orchestratorPrompt" not in page
    assert "textarea" not in page
    assert "worker=platform" + "-orchestrator" not in table
    assert "project=${encodeURIComponent(project.project_id)}" in table
    assert "Se eliminará definitivamente de la tabla de proyectos" in page
    assert 'window.confirm(\n      `Eliminar definitivamente "${project.name}"?' not in page
    assert '@router.post("/workspace/orchestrator/draft"' not in db_first_router
    assert '@router.post("/workspace/orchestrator/draft"' in managed_draft_router
    assert "workspace/orchestrator/" in bff_proxy
    assert "gateway_stale" in bff_proxy
    assert '@router.get("/workspace/projects"' in workspace_router
    assert '@router.post("/workspace/projects"' in workspace_router
    assert '@router.get("/workspace/projects"' not in db_first_router
    assert '@router.post("/workspace/projects"' not in db_first_router


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


def test_projects_catalog_links_to_project_detail_page() -> None:
    table = Path("apps/duckclaw-admin/src/components/projects/ProjectsTable.tsx").read_text(encoding="utf-8")
    detail_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/[projectId]/page.tsx")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    workspace_router = Path(
        "services/api-gateway/routers/admin_domains/workspace_projects.py"
    ).read_text(encoding="utf-8")
    db_first_router = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")

    assert detail_page.exists()
    detail_text = detail_page.read_text(encoding="utf-8")
    assert "getWorkspaceProject" in detail_text
    assert "ProjectAgentsSection" in detail_text
    assert "Contexto del proyecto" in detail_text
    assert "Conocimiento RAG" in detail_text
    assert "listKnowledgeSources" in detail_text
    assert "Gestionar RAG" in detail_text
    assert "Importar fuente" not in detail_text
    assert "Ver" in table
    assert "Eye" in table
    assert "href={`/projects/${encodeURIComponent(project.project_id)}`}" in table
    assert "overflow-x-auto" in table
    assert "min-w-[820px]" in table
    assert "whitespace-nowrap" in table
    assert "getWorkspaceProject:" in service
    assert "KnowledgeSource" in service
    assert "listKnowledgeSources:" in service
    assert "createKnowledgeSource:" in service
    assert "searchKnowledge:" in service
    assert '@router.get("/workspace/projects/{project_id}"' in workspace_router
    assert '@router.get("/workspace/projects/{project_id}"' not in db_first_router
    knowledge_router = Path("services/api-gateway/routers/admin_domains/knowledge.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/knowledge/sources"' in knowledge_router
    assert '@router.post("/knowledge/search"' in knowledge_router
    assert "projectDetailFallbackFromList" in bff_proxy
    assert "res.status === 405" in bff_proxy


def test_rag_manager_upload_contract_and_navigation() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    router = Path("services/api-gateway/routers/admin_domains/knowledge.py").read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")
    rag_page = Path("apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx")
    project_detail = Path("apps/duckclaw-admin/src/app/(admin)/projects/[projectId]/page.tsx").read_text(
        encoding="utf-8"
    )

    assert rag_page.exists()
    rag_text = rag_page.read_text(encoding="utf-8")
    assert "{ href: '/knowledge', label: 'RAG'" in nav
    assert "'/knowledge': Database" in Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(
        encoding="utf-8"
    )
    assert "Gestor RAG" in rag_text
    assert 'type="file"' in rag_text
    assert "multiple" in rag_text
    assert "webkitdirectory" in rag_text
    assert "uploadKnowledgeFiles" in rag_text
    assert "createKnowledgeSource" in rag_text
    assert "project_id" in rag_text
    assert "worker_uid" in rag_text
    assert "uploadKnowledgeFiles:" in service
    assert "FormData" in service
    assert '@router.post("/knowledge/uploads"' in router
    assert "UploadFile" in router
    assert "multipart/form-data" in bff_proxy
    assert "arrayBuffer" in bff_proxy
    assert 'href={`/knowledge?project=${encodeURIComponent(project.project_id)}`}' in project_detail


def test_prompt_policies_admin_ui_manages_managed_draft_without_seed_copy() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    page_path = Path("apps/duckclaw-admin/src/app/(admin)/policies/page.tsx")
    prompt_policy_router = Path(
        "services/api-gateway/routers/admin_domains/prompt_policies.py"
    ).read_text(encoding="utf-8")
    migrations = Path("packages/shared/src/duckclaw/schema_migrations.py").read_text(encoding="utf-8")

    assert page_path.exists()
    page = page_path.read_text(encoding="utf-8")
    assert "{ href: '/policies', label: 'Instrucciones'" in nav
    assert "'/policies': ClipboardList" in sidebar
    assert "PromptPolicy" in service
    assert "PromptPolicyHealth" in service
    assert "listPromptPolicies:" in service
    assert "getPromptPolicyHealth:" in service
    assert "upsertPromptPolicy:" in service
    assert "deactivatePromptPolicy:" in service
    assert "'/prompt-policies/health'" in service
    assert "`/prompt-policies${promptPoliciesQueryString(params)}`" in service
    assert "'/prompt-policies'" in service
    assert "method: 'DELETE'" in service
    assert "?version=${encodeURIComponent(String(version))}" in service
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in prompt_policy_router
    assert '@router.get("/health", dependencies=[Depends(require_admin_key)])' in prompt_policy_router
    assert '@router.put("", dependencies=[Depends(require_admin_key)])' in prompt_policy_router
    assert (
        '@router.delete("/{policy_type}/{policy_name}", dependencies=[Depends(require_admin_key)])'
        in prompt_policy_router
    )
    assert "DeactivatePromptPolicyCommand" in prompt_policy_router
    assert "MANAGED_DRAFT_POLICY_TYPE = 'manager_task'" in page
    assert "MANAGED_DRAFT_POLICY_NAME = 'admin_workspace_managed_draft'" in page
    assert "JSON.parse(content)" in page
    assert "Guardar borrador" in page
    assert "Estado" in page
    assert "humanHealthSummary" in page
    assert "getPromptPolicyHealth()" in page
    assert "missing_count" in page
    assert "adminService.upsertPromptPolicy" in page
    assert "adminService.deactivatePromptPolicy" in page
    assert "Desactivar versión" in page
    assert "No se borrará físicamente" in page
    assert "Esta acción desactiva solo la versión" in page
    assert "disabled={!canWrite" in page
    assert "_M019_MANAGED_WORKSPACE_DRAFT_POLICY" in migrations
    m020_segment = migrations.split("_M020_FRAMEWORK_CAPABILITY_POLICIES", 1)[1].split(
        "_M021_FRAMEWORK_POLICY_PACK", 1
    )[0]
    m021_segment = migrations.split("_M021_FRAMEWORK_POLICY_PACK", 1)[1].split("_MIGRATION_HOOKS", 1)[0]
    assert "admin_workspace_managed_draft" not in m020_segment
    assert "admin_workspace_managed_draft" not in m021_segment


def test_template_editor_explains_db_context_storage() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/templates/[workerId]/page.tsx").read_text(encoding="utf-8")

    assert "Dónde se almacena" in page
    assert "main.admin_worker_contexts" in page
    assert "system_prompt.md" in page
    assert "soul.md" in page
    assert "versiones del catálogo" in page


def test_playground_project_selection_forces_project_worker() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    project_rag = Path(
        "services/api-gateway/routers/admin_domains/playground/project_rag_context.py"
    ).read_text(encoding="utf-8")
    provider = Path("packages/agents/src/duckclaw/forge/rag/context_provider.py").read_text(encoding="utf-8")

    assert "firstProjectWorkerId" in page
    assert "workerBelongsToActiveProject" in page
    assert "syncProjectWorkerSelection" in page
    assert "setPlaygroundWorker" in page
    assert "worker actual no pertenece al proyecto" in page
    assert "build_knowledge_context" in project_rag
    assert "_knowledge_inventory_for_project" not in project_rag
    assert "RAG_SOURCE_INVENTORY" in provider
    assert "No confundas la base de conocimiento RAG con la bóveda DuckDB" in provider


def test_projects_catalog_and_managed_workspace_draft_are_separate_routes() -> None:
    projects_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
    wizard_page = Path("apps/duckclaw-admin/src/app/(admin)/projects/orchestrator/page.tsx").read_text(encoding="utf-8")
    wizard_component = Path(
        "apps/duckclaw-admin/src/components/projects/ProjectManagedWorkspaceDraftWizard.tsx"
    ).read_text(encoding="utf-8")

    assert 'href="/projects/orchestrator"' in projects_page
    assert "listWorkspaceProjectsPage" in projects_page
    assert "ProjectsCatalogToolbar" in projects_page
    assert "ProjectsTable" in projects_page
    assert "createOrchestratorDraft" not in projects_page
    assert "confirmOrchestratorDraft" not in projects_page
    assert "orchestratorPrompt" not in projects_page
    assert "ProjectManagedWorkspaceDraftWizard" in wizard_page
    assert "createManagedWorkspaceDraft" in wizard_component
    assert "confirmManagedWorkspaceDraft" in wizard_component
    assert "questionAnswers" in wizard_component
    assert "Análisis del borrador administrado" in wizard_component
    assert "htmlFor={answerId}" in wizard_component
    assert "managed-draft-question-${index}" in wizard_component
    assert "Respuesta opcional" in wizard_component
    assert "Continuar sin responder" in wizard_component
    assert "Para incorporarlas al borrador, ajusta el objetivo" in wizard_component


def test_managed_workspace_draft_copy_and_symbols_avoid_orchestrator_product_naming() -> None:
    """The legacy API path may say orchestrator; product/internal naming should not."""

    targets = [
        Path("apps/duckclaw-admin/src/app/(admin)/overview/page.tsx"),
        Path("apps/duckclaw-admin/src/app/(admin)/templates/page.tsx"),
        Path("apps/duckclaw-admin/src/app/(admin)/projects/orchestrator/page.tsx"),
        Path("apps/duckclaw-admin/src/components/projects/ProjectManagedWorkspaceDraftWizard.tsx"),
        Path("apps/duckclaw-admin/src/components/projects/ProjectsTable.tsx"),
        Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts"),
        Path("apps/duckclaw-admin/src/app/api/admin/forge-projects/route.ts"),
        Path("apps/duckclaw-admin/src/services/adminService.ts"),
        Path("services/api-gateway/routers/admin.py"),
        Path("services/api-gateway/routers/admin_db_first.py"),
        Path("services/api-gateway/routers/admin_domains/workspace_managed_draft.py"),
    ]
    forbidden = (
        "Platform Orchestrator",
        "Crear con Orchestrator",
        "con el Orchestrator",
        "el Orchestrator",
        "El Orchestrator",
        "Análisis del Orchestrator",
        "Analizar con Orchestrator",
        "ProjectOrchestratorWizard",
        "createOrchestratorDraft",
        "confirmOrchestratorDraft",
        "OrchestratorDraft",
        "OrchestratorConfirm",
        "_orchestrator_",
        "admin-orchestrator-draft",
        "workspace.orchestrator.confirm",
    )

    leaks = [
        f"{path}:{marker}"
        for path in targets
        if path.exists()
        for marker in forbidden
        if marker in path.read_text(encoding="utf-8")
    ]

    assert leaks == []


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


def test_topbar_can_restart_gateway_without_gateway_proxy() -> None:
    topbar = Path("apps/duckclaw-admin/src/components/layout/Topbar.tsx").read_text(encoding="utf-8")
    bff_proxy = Path("apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")
    errors = Path("apps/duckclaw-admin/src/lib/adminErrors.ts").read_text(encoding="utf-8")

    assert "adminService.runOps('pm2_restart_db_writer')" in topbar
    assert "adminService.runOps('pm2_restart_gateway')" in topbar
    assert "Reiniciar stack" in topbar
    assert "RefreshCw" in topbar
    assert "localOpsRunFallback" in bff_proxy
    assert "pm2_restart_db_writer" in bff_proxy
    assert "pm2_restart_gateway" in bff_proxy
    assert "start_stack" in bff_proxy
    assert "parseApiErrorDetail(data, res.status)" in service
    assert "looksLikeProblemContext" in errors


def test_manager_preserves_rag_blocks_for_worker_task() -> None:
    manager_invoke = Path(
        "packages/agents/src/duckclaw/manager/manager_nodes_invoke.py"
    ).read_text(encoding="utf-8")
    manager_helpers = Path(
        "packages/agents/src/duckclaw/manager/manager_invoke_helpers.py"
    ).read_text(encoding="utf-8")
    context_blocks = Path("packages/agents/src/duckclaw/forge/rag/context_blocks.py").read_text(encoding="utf-8")

    assert "from duckclaw.forge.rag.context_blocks import" in manager_invoke
    assert "preserve_context_blocks_for_worker" in manager_invoke
    assert "strip_tagged_blocks" in context_blocks
    assert "explicit_storage_request=explicit_duckdb_schema_request" in manager_invoke
    assert 'extract_tagged_block(incoming, "RAG_SOURCE_INVENTORY")' in context_blocks
    assert 'extract_tagged_block(incoming, "RAG_CONTEXT")' in context_blocks
    assert "Responde al usuario usando el contexto RAG disponible." in context_blocks
    assert "planned_task_for_worker = preserve_context_blocks_for_worker(" in manager_invoke
    assert '"input": planned_task_for_worker' in manager_helpers
    assert '"incoming": planned_task_for_worker' in manager_helpers
