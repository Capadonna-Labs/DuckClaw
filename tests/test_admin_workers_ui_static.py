from __future__ import annotations

from pathlib import Path

from admin_service_corpus import admin_service_corpus


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/page.tsx"
TEMPLATE_DETAIL_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/[workerId]/page.tsx"
WORKER_EDITOR_TABS = ROOT / "apps/duckclaw-admin/src/components/templates/WorkerEditorSectionTabs.tsx"
WORKER_CAPABILITIES_CARD = ROOT / "apps/duckclaw-admin/src/components/templates/WorkerCapabilitiesCard.tsx"
CREATE_AGENT_DIALOG = ROOT / "apps/duckclaw-admin/src/components/templates/CreateAgentDialog.tsx"
WORKER_ROLE_TEMPLATES = ROOT / "apps/duckclaw-admin/src/lib/workerRoleTemplates.ts"
WORKER_COMPOSITION_PRESETS = ROOT / "apps/duckclaw-admin/src/lib/workerCompositionPresets.ts"
POLICIES_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/policies/page.tsx"
POLICIES_VIEW = ROOT / "apps/duckclaw-admin/src/components/policies/PoliciesPageView.tsx"


def test_workers_ui_uses_generic_catalog_import_and_no_folder_delete_language() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = admin_service_corpus()

    assert "importTemplatesToCatalog" in service
    assert "/templates/import" in service
    assert "Nuevo agente" in page
    assert "catálogo DB-first" in page
    assert "Desactivar del catálogo" in page
    assert "Eliminar definitivo" in page
    assert "Se borrará la carpeta" not in page
    assert "rmtree" not in page
    assert "import_axis" not in page
    assert "import_axis" not in service
    assert "font-black" not in page
    assert "rounded-3xl" not in page


def test_workers_ui_lists_active_catalog_workers_only() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = admin_service_corpus()

    assert "showInactive" not in page
    assert "Mostrar inactivos" not in page
    assert "include_inactive: false" in page
    assert "reactivateTemplate" in service


def test_workers_ui_separates_deactivate_from_hard_delete() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = admin_service_corpus()

    assert "pendingDeactivate" in page
    assert "pendingHardDelete" in page
    assert "deactivateTemplate" in service
    assert "hardDeleteTemplate" in service
    assert "/hard-delete" in service
    assert "Sí, desactivar del catálogo" in page
    assert "Sí, eliminar definitivamente" in page
    assert "No borra carpetas de templates legacy" in page


def test_workers_ui_does_not_offer_deactivation_for_default_template() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")

    assert "isCatalogManaged" in page
    assert "showLifecycleActions" in page
    assert "canWrite && isCatalogManaged && !isProtectedWorker" in page
    assert "agent.source === 'catalog'" in page
    assert "agent.id === 'default'" in page


def test_worker_detail_ui_marks_catalog_workers_read_only() -> None:
    detail_page = TEMPLATE_DETAIL_PAGE.read_text(encoding="utf-8")
    tabs = WORKER_EDITOR_TABS.read_text(encoding="utf-8")

    assert "catálogo DB" in detail_page
    assert "isCatalogWorker" in detail_page
    assert "canEditFiles" in detail_page
    assert "WorkerEditorSectionTabs" in detail_page
    assert "Comportamiento" in tabs
    assert "Configurar herramientas" in WORKER_CAPABILITIES_CARD.read_text(encoding="utf-8")
    assert "WorkerCapabilitiesCard" in detail_page
    assert "Sin guardar" in detail_page
    assert "Añadir contexto" in detail_page
    assert "deleteTemplateContext" in detail_page
    assert "ConfirmDangerModal" in detail_page
    assert "Eliminar contexto seleccionado" in detail_page


def test_catalog_context_creation_gives_feedback_and_keeps_new_tab() -> None:
    detail_page = TEMPLATE_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "contextError" in detail_page
    assert "Escribe un nombre para el contexto" in detail_page
    assert "disabled={!title.trim()}" in detail_page
    assert "load(title)" in detail_page


def test_worker_editor_herramientas_includes_skill_picker() -> None:
    detail_page = TEMPLATE_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "WorkerSkillPickerPanel" in detail_page
    assert "WorkerMcpGrantsPanel" in detail_page
    assert "ManifestGuidedPanel" in detail_page
    assert "useSkillsCatalog" in detail_page


def test_create_agent_wizard_exposes_composition_panel() -> None:
    dialog = CREATE_AGENT_DIALOG.read_text(encoding="utf-8")
    roles = WORKER_ROLE_TEMPLATES.read_text(encoding="utf-8")
    presets = WORKER_COMPOSITION_PRESETS.read_text(encoding="utf-8")

    assert "WorkerCompositionPanel" in dialog
    assert "WorkerRoleTemplatePicker" in dialog
    assert "WorkerMcpGrantsPicker" in dialog
    assert "DEFAULT_TOOL_PROFILE" in dialog
    assert "pendingMcpConnectorIds" in dialog
    assert "pollWriteTask" in dialog
    assert "mergeSuggestedSkills" in dialog
    assert "applyRoleTemplateToDraft" in dialog
    assert "rounded-3xl" not in dialog
    assert "font-black" not in dialog
    assert "CAPABILITY_PRESETS" not in dialog
    assert "WORKER_ROLE_TEMPLATES" in roles
    assert "DEFAULT_TOOL_PROFILE" in roles
    assert "TOOL_PROFILE_LABELS" in presets
    assert "CAPABILITY_PRESETS" not in presets


def test_policies_page_redirects_to_plataforma_reglas() -> None:
    page = POLICIES_PAGE.read_text(encoding="utf-8")
    view = POLICIES_VIEW.read_text(encoding="utf-8")

    assert "redirect('/plataforma?tab=reglas')" in page
    assert "Reglas base" in view
    assert "listTemplates" in view
    assert "listPromptPolicies" in view
    assert "Listo" in view
    assert "Falta instrucciones" in view
    assert 'href={`/templates/${encodeURIComponent(agent.id)}`}' in view
    assert "forge/templates" not in view
