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


def test_sidebar_removes_inline_hide_menu_button_and_adds_playground_selector() -> None:
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")

    assert 'openLabel="Ocultar menú"' not in sidebar
    assert "consoleRoleLabel" not in sidebar
    assert "Rol activo:" not in sidebar
    assert "Historial" in sidebar
    assert "Tablero" in sidebar
    assert "Nueva conversación" in sidebar
    assert '/playground?view=history' in sidebar
    assert 'href="/kanban"' in sidebar
    assert "/playground?new=1" in sidebar
    assert "adminService.listConversations" not in sidebar


def test_playground_nav_groups_keep_kanban_nested_and_audit_in_security() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    operation_body = nav.split("export const OPERATION_NAV_GROUP", 1)[1].split(
        "export const BUILD_NAV_GROUP", 1
    )[0]
    build_body = nav.split("export const BUILD_NAV_GROUP", 1)[1].split(
        "export const DATA_NAV_GROUP", 1
    )[0]
    security_body = nav.split("export const SECURITY_NAV_GROUP", 1)[1].split(
        "export const SYSTEM_NAV_GROUP", 1
    )[0]
    system_body = nav.split("export const SYSTEM_NAV_GROUP", 1)[1].split(
        "/** Orden del sidebar", 1
    )[0]

    assert "label: 'Tablero'" not in operation_body
    assert "href: '/kanban'" not in operation_body
    assert "label: 'Auditoría'" not in operation_body
    assert "href: '/audit'" not in operation_body
    assert "label: 'Train'" in build_body
    assert "href: '/train'" in build_body
    assert "label: 'VNC'" in build_body
    assert "href: '/vnc'" in build_body
    assert "label: 'Auditoría'" in security_body
    assert "href: '/audit'" in security_body
    assert "label: 'Settings'" in security_body
    assert "href: '/settings'" in security_body
    assert "href: '/settings'" not in system_body
    assert "href: '/train'" not in system_body
    assert "href: '/vnc'" not in system_body
    assert "{ type: 'group', group: SYSTEM_NAV_GROUP }" not in nav


def test_integrations_are_nested_inside_agents_selector() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
    build_body = nav.split("export const BUILD_NAV_GROUP", 1)[1].split(
        "export const DATA_NAV_GROUP", 1
    )[0]
    structure_body = nav.split("export const ADMIN_NAV_STRUCTURE", 1)[1].split(
        "/** Lista plana", 1
    )[0]

    assert "label: 'Integraciones'" in build_body
    assert "href: '/integrations'" in build_body
    assert "{ type: 'group', group: INTEGRATIONS_NAV_GROUP }" not in structure_body
    assert "IntegrationsNavSelector" in sidebar
    assert "Telegram" in sidebar
    assert 'href="/telegram"' in sidebar
    assert "Edge devices" in sidebar
    assert 'href="/integrations/edge-devices"' in sidebar


def test_admin_sidebar_is_reduced_to_four_visible_groups() -> None:
    nav = Path("apps/duckclaw-admin/src/config/adminNav.ts").read_text(encoding="utf-8")
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
    structure_body = nav.split("export const ADMIN_NAV_STRUCTURE", 1)[1].split(
        "/** Lista plana", 1
    )[0]
    operation_body = nav.split("export const OPERATION_NAV_GROUP", 1)[1].split(
        "export const PLAYGROUND_NAV_GROUP", 1
    )[0]
    playground_body = nav.split("export const PLAYGROUND_NAV_GROUP", 1)[1].split(
        "export const BUILD_NAV_GROUP", 1
    )[0]
    build_body = nav.split("export const BUILD_NAV_GROUP", 1)[1].split(
        "export const DATA_NAV_GROUP", 1
    )[0]
    security_body = nav.split("export const SECURITY_NAV_GROUP", 1)[1].split(
        "export const SYSTEM_NAV_GROUP", 1
    )[0]

    assert "label: 'Inicio'" in operation_body
    assert "label: 'Playground'" in playground_body
    assert "label: 'Chat'" in playground_body
    assert "label: 'Agentes'" in build_body
    assert "label: 'Seguridad'" in security_body
    assert "{ type: 'group', group: OPERATION_NAV_GROUP }" in structure_body
    assert "{ type: 'group', group: PLAYGROUND_NAV_GROUP }" in structure_body
    assert "{ type: 'group', group: BUILD_NAV_GROUP }" in structure_body
    assert "{ type: 'group', group: SECURITY_NAV_GROUP }" in structure_body
    assert "{ type: 'group', group: DATA_NAV_GROUP }" not in structure_body
    assert "{ type: 'group', group: INTEGRATIONS_NAV_GROUP }" not in structure_body
    assert "{ type: 'group', group: SYSTEM_NAV_GROUP }" not in structure_body
    assert "hint:" not in operation_body
    assert "hint:" not in playground_body
    assert "hint:" not in build_body
    assert "hint:" not in security_body
    assert "openGroupId" in sidebar
    assert "openGroups" not in sidebar
    assert "group.hint" not in sidebar
    assert "rounded-2xl border border-white/10 bg-white/[0.03] p-2" not in sidebar


def test_topbar_hamburger_toggles_desktop_sidebar() -> None:
    topbar = Path("apps/duckclaw-admin/src/components/layout/Topbar.tsx").read_text(encoding="utf-8")

    assert "toggleSidebar" in topbar
    assert "lg:hidden" not in topbar
    assert "sidebarOpen ? 'Ocultar menú lateral' : 'Mostrar menú lateral'" in topbar


def test_user_logout_lives_in_topbar_user_menu_only() -> None:
    topbar = Path("apps/duckclaw-admin/src/components/layout/Topbar.tsx").read_text(encoding="utf-8")
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")

    assert "UserMenu" in topbar
    assert "userMenuOpen" in topbar
    assert "aria-label=\"Menú de usuario\"" in topbar
    assert "Cerrar sesión" in topbar
    assert "LogOut" in topbar
    assert "hidden md:inline\">Salir" not in topbar
    assert "className=\"flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/30\"" not in topbar
    assert "<footer" not in sidebar
    assert "Cerrar sesión" not in sidebar
    assert "roleDisplayName" not in sidebar


def test_playground_new_query_creates_new_conversation() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useActiveConversation.ts").read_text(encoding="utf-8")

    assert "const createConversation = useCallback" in hook
    assert "searchParams.get('new')" in page
    assert "bootstrapping: conversationBootstrapping" in page
    assert "createConversation()" in page
    assert "router.replace('/playground'" in page


def test_playground_selects_conversation_from_sidebar_history() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useActiveConversation.ts").read_text(encoding="utf-8")

    assert "ConversationInbox" not in page
    assert "PlaygroundHistoryView" in page
    assert "function uniqueConversationsBySession" in page
    assert "uniqueConversations.map((conversation)" in page
    assert "searchParams.get('view') === 'history'" in page
    assert "adminService.listConversations({ tenant_id: tenantId, section: 'playground', limit: 80 })" in page
    assert "href={`/playground?conversation=${encodeURIComponent(conversation.session_id)}`}" in page
    assert "const selectConversationById = useCallback" in hook
    assert "searchParams.get('conversation')" in page
    assert "selectConversationById(requestedConversation)" in page


def test_playground_config_panel_uses_live_vault_and_plain_labels() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")

    assert "const activeVaultPath = chat.vaultPath || config?.vault?.effective_path || ''" in page
    assert "activeVaultPath={activeVaultPath}" in page
    assert "effectivePath={activeVaultPath}" in page
    assert "Estado actual" in page
    assert "CurrentConfigSummary" in page
    assert "DuckDB" in page
    assert "Modelo fijado para esta conversación." in page
    assert "Run settings" not in page
    assert "Base URL" not in page
    assert "Override por conversación" not in page
    assert "equivalente a /model" not in page
    assert "config.team_hint" not in page
    assert "Equipo de este chat" not in page
    assert "Variables globales (.env)" not in page
    assert 'href="/settings"' not in page


def test_playground_config_panel_uses_single_open_accordions() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    toggle = Path("apps/duckclaw-admin/src/components/layout/PanelToggleButton.tsx").read_text(
        encoding="utf-8"
    )

    assert "type PlaygroundConfigSection = 'commands' | 'vault' | 'model' | 'instructions'" in page
    assert "const [openConfigSection, setOpenConfigSection] = useState<PlaygroundConfigSection>('commands')" in page
    assert "function ConfigAccordionSection" in page
    assert "onToggle={() => toggleConfigSection('commands')}" in page
    assert "onToggle={() => toggleConfigSection('vault')}" in page
    assert "onToggle={() => toggleConfigSection('model')}" in page
    assert "onToggle={() => toggleConfigSection('instructions')}" in page
    assert "title=\"Comandos\"" in page
    assert "title=\"Cambiar bóveda\"" in page
    assert "title=\"Cambiar modelo\"" in page
    assert "title=\"Instrucciones\"" in page
    assert "iconOnly?: boolean" in toggle
    assert "aria-label={label}" in toggle
    assert "{!iconOnly && label}" in toggle
    assert "const panelToggleTitle = panelOpen" in page
    assert "aria-label={panelToggleTitle}" in page
    assert "title={panelToggleTitle}" in page
    assert "panelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />" in page
    assert "fixed right-6 top-24 z-20" in page
    assert "top-1/2 -translate-y-1/2" not in page
    assert "openLabel=\"Ocultar panel\"" not in page
    assert "PanelToggleButton" not in page


def test_fly_commands_live_in_playground_not_overview() -> None:
    overview_ops = Path("apps/duckclaw-admin/src/components/admin/OverviewOpsPanel.tsx").read_text(
        encoding="utf-8"
    )
    playground = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(
        encoding="utf-8"
    )
    commands_page = Path("apps/duckclaw-admin/src/app/(admin)/commands/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "listFlyCommands" not in overview_ops
    assert "Fly Commands" not in overview_ops
    assert "ChatCommandsPanel" in playground
    assert "Comandos del chat" in playground
    assert "Comandos frecuentes" in playground
    assert "Ver todos" in playground
    assert "listFlyCommands" in playground
    assert "redirect('/playground')" in commands_page


def test_overview_combines_operations_and_pm2_logs() -> None:
    overview_ops = Path("apps/duckclaw-admin/src/components/admin/OverviewOpsPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "Operaciones y logs" in overview_ops
    assert "StackBootstrapPanel compact onConnected={onHealthReload}" in overview_ops
    assert "Pm2LiveLogsPanel embedded" in overview_ops
    assert "Salida de la operación" in overview_ops
    assert "Las acciones dejan huella aquí" in overview_ops
    assert "items-start" in overview_ops
    assert "max-h-[420px] overflow-y-auto pr-1" in overview_ops
    assert "self-start xl:sticky xl:top-4" in overview_ops
    assert 'titulo="Operaciones"' not in overview_ops
    assert 'titulo="PM2 logs en vivo"' not in overview_ops
    assert "SettingsSection" not in overview_ops


def test_floating_chat_uses_fixed_large_panel_and_header_actions() -> None:
    floating = Path("apps/duckclaw-admin/src/components/chat/FloatingAdminChat.tsx").read_text(
        encoding="utf-8"
    )
    panel = Path("apps/duckclaw-admin/src/components/chat/AdminChatPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "const PANEL_WIDTH_PX = 560" in floating
    assert "const PANEL_HEIGHT_PX = 720" in floating
    assert "width: PANEL_WIDTH_PX" in floating
    assert "height: `min(${PANEL_HEIGHT_PX}px, calc(100vh - 2rem))`" in floating
    assert "headerActions={" in floating
    assert "aria-label=\"Mostrar conversaciones\"" in floating
    assert "aria-label=\"Abrir Playground completo\"" in floating
    assert "aria-label={loading ? 'Minimizar chat (el agente sigue pensando)' : 'Cerrar chat'}" in floating
    assert "Redimensionar ventana de chat" not in floating
    assert "PANEL_WIDTH_STORAGE_KEY" not in floating
    assert "PANEL_HEIGHT_STORAGE_KEY" not in floating
    assert "resizeRef" not in floating
    assert "headerActions?: React.ReactNode" in panel
    assert "{headerActions}" in panel


def test_admin_pages_avoid_internal_jargon_copy() -> None:
    targets = [
        "apps/duckclaw-admin/src/app/(admin)/projects/page.tsx",
        "apps/duckclaw-admin/src/app/(admin)/skills/page.tsx",
        "apps/duckclaw-admin/src/app/(admin)/mcp/page.tsx",
        "apps/duckclaw-admin/src/app/(admin)/telegram/page.tsx",
        "apps/duckclaw-admin/src/app/(admin)/admin/access/page.tsx",
        "apps/duckclaw-admin/src/components/access/AccessPersistenceInfo.tsx",
        "apps/duckclaw-admin/src/app/(admin)/templates/page.tsx",
        "apps/duckclaw-admin/src/app/(admin)/playground/page.tsx",
    ]
    banned = [
        "Mostrando máximo 5 por página",
        "Relación normalizada",
        "admin_project_agents",
        "Agrupaciones DB-first",
        "Átomos Python",
        "workers DB-first",
        "MCP primero",
        "Servidor HTTP DuckClaw",
        "Skills personalizadas (Python)",
        "Progressive disclosure",
        "Whitelist Telegram Guard",
        "main.authorized_users",
        "Fuente de verdad para login",
        "manifests ni contextos",
        "tenant_id =",
    ]
    combined = "\n".join(Path(path).read_text(encoding="utf-8") for path in targets)

    for phrase in banned:
        assert phrase not in combined


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
