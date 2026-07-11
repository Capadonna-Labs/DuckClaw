from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/page.tsx"
TEMPLATE_DETAIL_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/[workerId]/page.tsx"
POLICIES_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/policies/page.tsx"
ADMIN_SERVICE = ROOT / "apps/duckclaw-admin/src/services/adminService.ts"


def test_workers_ui_uses_generic_catalog_import_and_no_folder_delete_language() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = ADMIN_SERVICE.read_text(encoding="utf-8")

    assert "importTemplatesToCatalog" in service
    assert "/templates/import" in service
    assert "Crear borrador administrado" in page
    assert "catálogo DB-first" in page
    assert "Desactivar del catálogo" in page
    assert "Eliminar definitivo" in page
    assert "Se borrará la carpeta" not in page
    assert "rmtree" not in page
    assert "import_axis" not in page
    assert "import_axis" not in service


def test_workers_ui_lists_active_catalog_workers_only() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = ADMIN_SERVICE.read_text(encoding="utf-8")

    assert "showInactive" not in page
    assert "Mostrar inactivos" not in page
    assert "include_inactive: false" in page
    assert "reactivateTemplate" in service


def test_workers_ui_separates_deactivate_from_hard_delete() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = ADMIN_SERVICE.read_text(encoding="utf-8")

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
    assert "canWrite && isCatalogManaged && !isProtectedWorker" in page
    assert "{!isInactive && (" in page
    assert "agent.source === 'catalog'" in page
    assert "agent.id === 'default'" in page


def test_worker_detail_ui_marks_catalog_workers_read_only() -> None:
    detail_page = TEMPLATE_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "catálogo DB" in detail_page
    assert "isCatalogWorker" in detail_page
    assert "canEditFiles" in detail_page
    assert "Snapshot importado desde DuckDB" in detail_page
    assert "Guardado en DuckDB (catálogo)" in detail_page
    assert "no modifican" in detail_page
    assert "CatalogContextTools" in detail_page
    assert "Añadir contexto" in detail_page
    assert "deleteTemplateContext" in detail_page
    assert "reorderTemplateContexts" in detail_page


def test_catalog_context_creation_gives_feedback_and_keeps_new_tab() -> None:
    detail_page = TEMPLATE_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "contextError" in detail_page
    assert "Escribe un nombre para el contexto" in detail_page
    assert "disabled={!title.trim()}" in detail_page
    assert "load(title)" in detail_page


def test_policies_page_surfaces_agent_capabilities_without_legacy_paths() -> None:
    page = POLICIES_PAGE.read_text(encoding="utf-8")

    assert "Tus agentes" in page
    assert "Reglas base" in page
    assert "¿Qué sigue?" in page
    assert "listTemplates" in page
    assert "listPromptPolicies" in page
    assert "skills_list" in page
    assert "Listo" in page
    assert "Falta instrucciones" in page
    assert 'href={`/templates/${encodeURIComponent(agent.id)}`}' in page
    assert "forge/templates" not in page
    assert "tenant" not in page.lower()
