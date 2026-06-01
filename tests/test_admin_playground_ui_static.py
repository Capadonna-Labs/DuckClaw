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


def test_active_conversation_is_scoped_by_authenticated_tenant() -> None:
    storage = Path("apps/duckclaw-admin/src/lib/conversationStorage.ts").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useActiveConversation.ts").read_text(encoding="utf-8")

    assert "activeConversationKey(tenantId)" in storage
    assert "readActiveConversationId(tid)" in hook
    assert "writeActiveConversationId(id, tid)" in hook
    assert "const created = await adminService.createConversation({ section }, tid)" in hook


def test_admin_chat_status_text_uses_plain_labels_without_emoji() -> None:
    heartbeat = Path("apps/duckclaw-admin/src/lib/toolHeartbeat.ts").read_text(encoding="utf-8")
    chat = Path("apps/duckclaw-admin/src/components/chat/ChatBubble.tsx").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useAdminChat.ts").read_text(encoding="utf-8")

    assert "const base = `Usando: ${name}`" in heartbeat
    assert "`Usando: ${toolName}`" in chat
    assert "Tiempo: ${(meta.elapsed_ms / 1000).toFixed(2)}s" in hook
    assert "const base = `🔄 Usando: ${name}`" not in heartbeat
    assert "return `⏱️" not in heartbeat
    assert "running ? ' · ⏱️" not in chat


def test_skills_catalog_fallback_does_not_scan_filesystem_templates() -> None:
    fallback = Path("apps/duckclaw-admin/src/lib/adminCatalogFallback.ts").read_text(encoding="utf-8")

    body = fallback.split("export function fallbackSkillsCatalog()", 1)[1].split(
        "export function fallbackMcpCatalog()", 1
    )[0]
    assert "global: []" in body
    assert "template_local: []" in body
    assert "readdirSync" not in body
    assert "forge/templates" not in body


def test_projects_page_only_renders_db_first_projects() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")

    assert "listForgeProjects" not in page
    assert "Legacy filesystem" not in page
    assert "forge/projects/" not in page


def test_kanban_storage_is_scoped_by_authenticated_actor() -> None:
    route = Path("apps/duckclaw-admin/src/app/api/admin/kanban/route.ts").read_text(encoding="utf-8")

    assert "storePath(actor: string)" in route
    assert "kanbanStoreActorKey(actor)" in route
    assert "loadCards(auth.actor)" in route
    assert "saveCards(auth.actor, cards)" in route
    assert "admin-kanban.json" not in route


def test_mcp_page_does_not_render_official_reference_as_user_catalog() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/mcp/page.tsx").read_text(encoding="utf-8")

    assert "OfficialMcpReferenceTable" not in page
    assert "Servidores de referencia" not in page
    assert "MCP Registry" not in page


def test_console_user_delete_uses_confirm_danger_modal() -> None:
    panel = Path("apps/duckclaw-admin/src/components/access/ConsoleUsersPanel.tsx").read_text(encoding="utf-8")

    assert "ConfirmDangerModal" in panel
    assert "pendingDeactivate" in panel
    assert "confirm(`" not in panel
    assert "title=\"Desactivar usuario\"" in panel


def test_skills_page_exposes_new_skill_db_first_form() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/skills/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "Nueva skill" in page
    assert "createSkill" in page
    assert "implementationRef" in page
    assert "createSkill:" in service


def test_duckdb_page_exposes_confirmed_legacy_schema_cleanup() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/duckdb/page.tsx").read_text(encoding="utf-8")
    service = Path("apps/duckclaw-admin/src/services/adminService.ts").read_text(encoding="utf-8")

    assert "Schemas legacy detectados" in page
    assert "ConfirmDangerModal" in page
    assert "DROP_LEGACY_SCHEMAS" in page
    assert "listDuckdbLegacySchemas" in service
    assert "dropDuckdbLegacySchemas" in service
