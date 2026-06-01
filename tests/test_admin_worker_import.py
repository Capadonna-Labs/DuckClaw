from __future__ import annotations

from pathlib import Path

import duckdb


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def _write_template(root: Path, name: str, *, display_name: str = "AXIS Coder") -> Path:
    template = root / name
    template.mkdir(parents=True)
    (template / "manifest.yaml").write_text(
        "\n".join(
            [
                f"id: {name}",
                "agent_id: coder",
                f'display_name: "{display_name}"',
                'description: "Template de prueba"',
                "dependencies:",
                "  capabilities_required:",
                "    - CAP-CODER-001",
                "    - CAP-CODER-002",
                'llm_config:',
                '  system_prompt_file: "./system_prompt.md"',
                'domain_closure_file: "./domain_closure.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (template / "system_prompt.md").write_text("# Sistema\nAyuda a programar.\n", encoding="utf-8")
    (template / "domain_closure.md").write_text("# Dominio\nSolo repo local.\n", encoding="utf-8")
    (template / "schema.sql").write_text("CREATE TABLE example(id VARCHAR);\n", encoding="utf-8")
    return template


def test_import_templates_to_catalog_is_selective_idempotent_and_non_destructive(
    gateway_db: Path,
    tmp_path: Path,
) -> None:
    from duckclaw.admin_template_import import import_templates_to_catalog
    from duckclaw.admin_worker_catalog import (
        list_worker_capabilities,
        list_worker_contexts,
        list_visible_workers_for_actor,
    )

    templates_root = tmp_path / "templates"
    axis_template = _write_template(templates_root, "AXIS-Coder", display_name="AXIS Coder")
    other_template = _write_template(templates_root, "Other-Dev", display_name="Other Dev")
    before_axis_files = sorted(p.relative_to(axis_template) for p in axis_template.rglob("*") if p.is_file())
    before_other_files = sorted(p.relative_to(other_template) for p in other_template.rglob("*") if p.is_file())

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        first = import_templates_to_catalog(
            adapter,
            owner_email="admin@test.local",
            templates_root=templates_root,
            include_prefixes=("AXIS-",),
        )
        second = import_templates_to_catalog(
            adapter,
            owner_email="admin@test.local",
            templates_root=templates_root,
            include_prefixes=("AXIS-",),
        )
        visible = list_visible_workers_for_actor(adapter, actor_email="admin@test.local")
        axis_worker = next(worker for worker in visible if worker["id"] == "axis-coder")
        contexts = list_worker_contexts(adapter, worker_uid=axis_worker["worker_uid"])
        capabilities = list_worker_capabilities(adapter, worker_uid=axis_worker["worker_uid"])
        version_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_versions WHERE worker_uid = ?",
            [axis_worker["worker_uid"]],
        ).fetchone()[0]
    finally:
        con.close()

    after_axis_files = sorted(p.relative_to(axis_template) for p in axis_template.rglob("*") if p.is_file())
    after_other_files = sorted(p.relative_to(other_template) for p in other_template.rglob("*") if p.is_file())

    assert [item["worker_id"] for item in first["imported"]] == ["axis-coder"]
    assert second["imported"] == []
    assert second["skipped_existing"] == ["axis-coder"]
    assert "other-dev" not in {worker["id"] for worker in visible}
    assert [context["title"] for context in contexts] == ["domain_closure.md", "system_prompt.md"]
    assert {capability["name"] for capability in capabilities} == {"CAP-CODER-001", "CAP-CODER-002"}
    assert version_count == 1
    assert before_axis_files == after_axis_files
    assert before_other_files == after_other_files


def test_import_templates_can_include_explicit_prefix_without_deleting_it(
    gateway_db: Path,
    tmp_path: Path,
) -> None:
    from duckclaw.admin_template_import import import_templates_to_catalog
    from duckclaw.admin_worker_catalog import list_visible_workers_for_actor

    templates_root = tmp_path / "templates"
    other_template = _write_template(templates_root, "Other-Dev", display_name="Other Dev")
    before_files = sorted(p.relative_to(other_template) for p in other_template.rglob("*") if p.is_file())

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        result = import_templates_to_catalog(
            adapter,
            owner_email="admin@test.local",
            templates_root=templates_root,
            include_prefixes=("Other-",),
        )
        visible = list_visible_workers_for_actor(adapter, actor_email="admin@test.local")
    finally:
        con.close()

    after_files = sorted(p.relative_to(other_template) for p in other_template.rglob("*") if p.is_file())

    assert [item["worker_id"] for item in result["imported"]] == ["other-dev"]
    assert "other-dev" in {worker["id"] for worker in visible}
    assert before_files == after_files


def test_template_import_script_apply_import_uses_db_path_and_templates_root(
    gateway_db: Path,
    tmp_path: Path,
) -> None:
    import importlib

    from duckclaw.admin_worker_catalog import list_visible_workers_for_actor

    templates_root = tmp_path / "templates"
    _write_template(templates_root, "AXIS-Coder", display_name="AXIS Coder")
    script = importlib.import_module("scripts.import_templates_to_catalog")

    result = script.apply_import(
        db_path=str(gateway_db),
        owner_email="admin@test.local",
        templates_root=str(templates_root),
        include_prefixes=("AXIS-",),
    )

    con = duckdb.connect(str(gateway_db))
    try:
        visible = list_visible_workers_for_actor(_Adapter(con), actor_email="admin@test.local")
    finally:
        con.close()

    assert [item["worker_id"] for item in result["imported"]] == ["axis-coder"]
    assert "axis-coder" in {worker["id"] for worker in visible}


def test_template_import_module_and_script_do_not_hardcode_axis() -> None:
    import inspect

    import scripts.import_templates_to_catalog as cli
    from duckclaw import admin_template_import

    module_source = inspect.getsource(admin_template_import)
    cli_source = inspect.getsource(cli)

    assert "AXIS" not in module_source
    assert "import_axis" not in module_source
    assert "AXIS" not in cli_source
    assert "import_axis" not in cli_source


def test_gateway_import_templates_endpoint_imports_selected_prefix_without_deleting_folders(
    gateway_admin_client,
    tmp_path: Path,
) -> None:
    templates_root = tmp_path / "templates"
    selected = _write_template(templates_root, "Selected-Agent", display_name="Selected Agent")
    ignored = _write_template(templates_root, "Ignored-Agent", display_name="Ignored Agent")
    before_selected = sorted(p.relative_to(selected) for p in selected.rglob("*") if p.is_file())
    before_ignored = sorted(p.relative_to(ignored) for p in ignored.rglob("*") if p.is_file())

    response = gateway_admin_client.post(
        "/api/v1/admin/templates/import",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"templates_root": str(templates_root), "include_prefixes": ["Selected-"]},
    )

    after_selected = sorted(p.relative_to(selected) for p in selected.rglob("*") if p.is_file())
    after_ignored = sorted(p.relative_to(ignored) for p in ignored.rglob("*") if p.is_file())

    assert response.status_code == 200
    data = response.json()
    assert [item["worker_id"] for item in data["imported"]] == ["selected-agent"]
    assert data["skipped_existing"] == []
    assert before_selected == after_selected
    assert before_ignored == after_ignored

    listed = gateway_admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    templates = {item["id"] for item in listed.json()["templates"]}
    assert "selected-agent" in templates
    assert "ignored-agent" not in templates


def test_gateway_template_detail_reads_imported_catalog_snapshot_without_template_folder(
    gateway_admin_client,
    tmp_path: Path,
) -> None:
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "Selected-Agent", display_name="Selected Agent")

    imported = gateway_admin_client.post(
        "/api/v1/admin/templates/import",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"templates_root": str(templates_root), "include_prefixes": ["Selected-"]},
    )
    assert imported.status_code == 200

    detail = gateway_admin_client.get(
        "/api/v1/admin/templates/selected-agent",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == "selected-agent"
    assert data["source"] == "catalog"
    assert data["read_only"] is True
    assert "manifest.yaml" in data["contents"]
    assert "system_prompt.md" in data["contents"]
    assert any(item["path"] == "system_prompt.md" for item in data["files"])


def test_gateway_template_file_save_updates_catalog_context_and_version_without_touching_folder(
    gateway_admin_client,
    tmp_path: Path,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import (
        get_latest_worker_version,
        get_visible_worker_for_actor,
        list_worker_contexts,
    )
    from duckclaw.gateway_db import get_gateway_db_path

    templates_root = tmp_path / "templates"
    template_dir = _write_template(templates_root, "Selected-Agent", display_name="Selected Agent")
    before_files = {
        str(path.relative_to(template_dir)): path.read_text(encoding="utf-8")
        for path in template_dir.rglob("*")
        if path.is_file()
    }
    imported = gateway_admin_client.post(
        "/api/v1/admin/templates/import",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"templates_root": str(templates_root), "include_prefixes": ["Selected-"]},
    )
    assert imported.status_code == 200

    response = gateway_admin_client.put(
        "/api/v1/admin/templates/selected-agent/files/system_prompt.md",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"content": "# Nuevo prompt\n\nDB-first"},
    )

    after_files = {
        str(path.relative_to(template_dir)): path.read_text(encoding="utf-8")
        for path in template_dir.rglob("*")
        if path.is_file()
    }
    assert response.status_code == 200
    assert response.json()["source"] == "catalog"
    assert before_files == after_files

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        worker = get_visible_worker_for_actor(db, actor_email="admin@test.local", worker_id="selected-agent")
        assert worker is not None
        contexts = {ctx["title"]: ctx["content_md"] for ctx in list_worker_contexts(db, worker_uid=worker["worker_uid"])}
        latest = get_latest_worker_version(db, worker_uid=worker["worker_uid"])
    finally:
        db.close()
    assert contexts["system_prompt.md"] == "# Nuevo prompt\n\nDB-first"
    assert latest is not None
    assert int(latest["version"]) == 2
    assert latest["files_snapshot"]["system_prompt.md"] == "# Nuevo prompt\n\nDB-first"


def test_gateway_catalog_context_crud_adds_reorders_and_deactivates_context(
    gateway_admin_client,
    tmp_path: Path,
) -> None:
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "Selected-Agent", display_name="Selected Agent")
    imported = gateway_admin_client.post(
        "/api/v1/admin/templates/import",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"templates_root": str(templates_root), "include_prefixes": ["Selected-"]},
    )
    assert imported.status_code == 200

    created = gateway_admin_client.post(
        "/api/v1/admin/templates/selected-agent/contexts",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"title": "extra_context.md", "content_md": "# Extra\n\nNuevo contexto", "sort_order": 1},
    )
    assert created.status_code == 200
    context_id = created.json()["context"]["context_id"]

    detail = gateway_admin_client.get(
        "/api/v1/admin/templates/selected-agent",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    data = detail.json()
    assert data["contents"]["extra_context.md"] == "# Extra\n\nNuevo contexto"
    assert any(ctx["context_id"] == context_id for ctx in data["contexts"])

    reordered = gateway_admin_client.patch(
        "/api/v1/admin/templates/selected-agent/contexts/reorder",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"items": [{"context_id": context_id, "sort_order": 50}]},
    )
    assert reordered.status_code == 200
    assert reordered.json()["updated"] == 1

    deleted = gateway_admin_client.delete(
        f"/api/v1/admin/templates/selected-agent/contexts/{context_id}",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    assert deleted.status_code == 200

    detail_after = gateway_admin_client.get(
        "/api/v1/admin/templates/selected-agent",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    after = detail_after.json()
    assert "extra_context.md" not in after["contents"]
    assert all(ctx["context_id"] != context_id for ctx in after["contexts"])


def test_gateway_delete_template_deactivates_catalog_worker_without_deleting_template_folder(
    gateway_admin_client,
    tmp_path: Path,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path

    template_dir = _write_template(tmp_path / "templates", "Selected-Agent", display_name="Selected Agent")
    before_files = sorted(p.relative_to(template_dir) for p in template_dir.rglob("*") if p.is_file())

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="selected-agent",
            display_name="Selected Agent",
        )
    finally:
        db.close()

    response = gateway_admin_client.delete(
        "/api/v1/admin/templates/selected-agent",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    after_files = sorted(p.relative_to(template_dir) for p in template_dir.rglob("*") if p.is_file())

    assert response.status_code == 200
    assert response.json()["action"] == "deactivated"
    assert before_files == after_files

    listed = gateway_admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )
    templates = {item["id"] for item in listed.json()["templates"]}
    assert "selected-agent" not in templates
