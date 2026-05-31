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
