from __future__ import annotations

from pathlib import Path


def test_user_facing_python_copy_avoids_forge_templates_paths() -> None:
    workers = Path("packages/agents/src/duckclaw/commands/workers.py").read_text(encoding="utf-8")
    manager = Path("packages/agents/src/duckclaw/manager/manager_nodes_invoke.py").read_text(encoding="utf-8")
    catalog = Path("packages/duckops/duckops/sovereign/workers_catalog.py").read_text(encoding="utf-8")
    meta = Path("services/api-gateway/routers/admin_domains/catalog_meta.py").read_text(encoding="utf-8")

    assert "No hay agentes en el catálogo" in workers
    assert "forge/templates" not in workers

    assert "No hay agentes configurados en el catálogo" in manager
    assert "forge/templates (con manifest.yaml)" not in manager

    assert "No se encontraron agentes en el catálogo" in catalog
    assert "No se encontraron plantillas en forge/templates" not in catalog

    assert 'subtitle = f"Agente del catálogo ({template_id})"' in meta
    assert 'Plantilla forge/templates/' not in meta
