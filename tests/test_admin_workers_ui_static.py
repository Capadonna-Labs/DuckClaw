from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/page.tsx"
TEMPLATE_DETAIL_PAGE = ROOT / "apps/duckclaw-admin/src/app/(admin)/templates/[workerId]/page.tsx"
ADMIN_SERVICE = ROOT / "apps/duckclaw-admin/src/services/adminService.ts"


def test_workers_ui_uses_generic_catalog_import_and_no_folder_delete_language() -> None:
    page = TEMPLATES_PAGE.read_text(encoding="utf-8")
    service = ADMIN_SERVICE.read_text(encoding="utf-8")

    assert "importTemplatesToCatalog" in service
    assert "/templates/import" in service
    assert "Importar templates" in page
    assert "include_prefixes" in page
    assert "Desactivar del catálogo" in page
    assert "Se borrará la carpeta" not in page
    assert "rmtree" not in page
    assert "import_axis" not in page
    assert "import_axis" not in service


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
