"""Tests for Report Engine core."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from duckclaw.report_engine.analyzer import analyze_docx_template
from duckclaw.report_engine.preview import render_preview_html
from duckclaw.report_engine.state import init_state_from_schema, patch_section, summarize_status
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_command_handlers import dispatch_command


def test_analyze_corporate_seed_template() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "packages/shared/src/duckclaw/seeds/document_templates/corporate_report.docx"
    )
    if not path.is_file():
        import pytest

        pytest.skip("corporate_report.docx seed missing — run scripts/seed_corporate_docx_template.py")
    analysis = analyze_docx_template(path)
    ids = {s["id"] for s in analysis["sections"]}
    assert "title" in ids
    assert "body" in ids


def test_analyze_plain_docx_fails_loud(tmp_path: Path) -> None:
    from docx import Document
    import pytest

    target = tmp_path / "informe_libre.docx"
    doc = Document()
    doc.add_paragraph("Informe mensual de gestión sin placeholders Jinja.")
    doc.save(str(target))
    with pytest.raises(ValueError, match="No se detectaron secciones"):
        analyze_docx_template(target)


def test_analyze_dotted_jinja_placeholders(tmp_path: Path) -> None:
    from docx import Document

    target = tmp_path / "dotted.docx"
    doc = Document()
    doc.add_paragraph("Campo {{ evidencia2.1 }} y {{ body }}")
    doc.save(str(target))
    analysis = analyze_docx_template(target)
    ids = {s["id"] for s in analysis["sections"]}
    assert "evidencia2.1" in ids
    assert "body" in ids
    assert "editable_field_count" in analysis


def test_build_render_context_nests_dotted_ids() -> None:
    from duckclaw.report_engine.state import build_render_context, init_state_from_schema, patch_section

    schema = [{"id": "evidencia2.1", "label": "E2.1"}, {"id": "body", "label": "Body"}]
    state = init_state_from_schema(schema)
    state = patch_section(state, section_id="evidencia2.1", content="Hecho A", mode="replace")
    state = patch_section(state, section_id="body", content="Cuerpo", mode="replace")
    ctx = build_render_context(state)
    assert ctx["body"] == "Cuerpo"
    assert ctx["evidencia2"]["1"] == "Hecho A"


def test_markdown_table_collapses_for_docx_cells() -> None:
    from duckclaw.report_engine.docx_content import content_to_docxtpl_value, markdown_tables_to_plain

    md = "| Actividad | Estado |\n|---|---|\n| A | OK |"
    plain = markdown_tables_to_plain(md)
    assert "|" not in plain
    assert "Actividad" in plain and "OK" in plain
    val = content_to_docxtpl_value(md)
    assert val != ""


def test_render_preserves_word_table(tmp_path: Path) -> None:
    from docx import Document

    from duckclaw.report_engine.render import render_instance_docx_from_uri
    from duckclaw.report_engine.state import init_state_from_schema, patch_section

    tpl = tmp_path / "tpl.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "{{ field_a }}"
    table.cell(0, 1).text = "Fijo"
    table.cell(1, 0).text = "{{ field_b }}"
    table.cell(1, 1).text = "Pie"
    doc.save(str(tpl))

    schema = [{"id": "field_a", "label": "A"}, {"id": "field_b", "label": "B"}]
    state = init_state_from_schema(schema)
    state = patch_section(
        state,
        section_id="field_a",
        content="Línea 1\nLínea 2",
        mode="replace",
    )
    state = patch_section(state, section_id="field_b", content="Valor B", mode="replace")

    out_root = tmp_path / "out"
    rendered = render_instance_docx_from_uri(
        template_uri=str(tpl),
        state_json=__import__("json").dumps(state),
        output_root=out_root,
        instance_id="rpt_tbl",
        title="Test",
    )
    result = Document(str(rendered["path"]))
    assert len(result.tables) == 1
    cell_text = result.tables[0].cell(0, 0).text
    assert "Línea 1" in cell_text and "Línea 2" in cell_text
    assert "Valor B" in result.tables[0].cell(1, 0).text
    assert "Fijo" in result.tables[0].cell(0, 1).text


def test_patch_section_append_and_status() -> None:
    schema = [{"id": "obligaciones_1", "label": "Obligaciones 1"}]
    state = init_state_from_schema(schema)
    state = patch_section(state, section_id="obligaciones_1", content="Reunión X", mode="append")
    state = patch_section(state, section_id="obligaciones_1", content="Entrega Y", mode="append")
    summary = summarize_status(state, schema)
    assert summary["partial_count"] == 1
    state = patch_section(
        state,
        section_id="obligaciones_1",
        content="",
        mode="replace",
        mark_complete=True,
    )
    # replace with empty but mark_complete still partial/empty - test mark complete with content
    state = patch_section(
        state,
        section_id="obligaciones_1",
        content="Cierre",
        mode="replace",
        mark_complete=True,
    )
    summary = summarize_status(state, schema)
    assert summary["complete_count"] == 1


def test_report_engine_migration_and_handlers(tmp_path: Path) -> None:
    db = duckdb.connect(str(tmp_path / "hub.duckdb"))
    run_pending_migrations(db)
    schema = [{"id": "intro", "label": "Introducción"}]
    dispatch_command(
        db,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_demo",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "name": "Demo",
            "template_uri": "/vault/demo.docx",
            "section_schema": schema,
            "analyzer_mode": "jinja",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "create_report_instance",
            "instance_id": "rpt_demo",
            "template_id": "tpl_demo",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "title": "Informe Junio",
            "period_key": "2026-06",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "patch_report_section",
            "instance_id": "rpt_demo",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "section_id": "intro",
            "content": "Avance del mes",
            "mode": "replace",
        },
    )
    row = db.execute(
        "SELECT state_json, preview_html FROM main.admin_report_instances WHERE instance_id = 'rpt_demo'"
    ).fetchone()
    assert row is not None
    state = json.loads(str(row[0]))
    assert "Avance" in state["sections"]["intro"]["content"]
    assert "<!DOCTYPE html>" in str(row[1])


def test_soft_delete_report_template_archives_owned_instances(tmp_path: Path) -> None:
    db = duckdb.connect(str(tmp_path / "hub_tpl_del.duckdb"))
    run_pending_migrations(db)
    dispatch_command(
        db,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_del_t",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "name": "ToDelete",
            "template_uri": "/vault/t.docx",
            "section_schema": [{"id": "body"}],
            "analyzer_mode": "jinja",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "create_report_instance",
            "instance_id": "rpt_owned",
            "template_id": "tpl_del_t",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "title": "Owned",
            "period_key": "2026-08",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "soft_delete_report_template",
            "template_id": "tpl_del_t",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
        },
    )
    tpl = db.execute(
        "SELECT active FROM main.admin_report_templates WHERE template_id = 'tpl_del_t'"
    ).fetchone()
    inst = db.execute(
        "SELECT active, status FROM main.admin_report_instances WHERE instance_id = 'rpt_owned'"
    ).fetchone()
    assert tpl is not None and tpl[0] is False
    assert inst is not None and inst[0] is False and str(inst[1]) == "archived"


def test_soft_delete_report_instance_allows_new_create(tmp_path: Path) -> None:
    db = duckdb.connect(str(tmp_path / "hub_soft_del.duckdb"))
    run_pending_migrations(db)
    schema = [{"id": "body", "label": "Body"}]
    dispatch_command(
        db,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_del",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "name": "Del",
            "template_uri": "/vault/d.docx",
            "section_schema": schema,
            "analyzer_mode": "jinja",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "create_report_instance",
            "instance_id": "rpt_del",
            "template_id": "tpl_del",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "title": "Borrador a eliminar",
        },
    )
    dispatch_command(
        db,
        {
            "command_type": "soft_delete_report_instance",
            "instance_id": "rpt_del",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
        },
    )
    row = db.execute(
        "SELECT active, status FROM main.admin_report_instances WHERE instance_id = 'rpt_del'"
    ).fetchone()
    assert row is not None
    assert row[0] is False
    assert str(row[1]) == "archived"
    dispatch_command(
        db,
        {
            "command_type": "create_report_instance",
            "instance_id": "rpt_del_2",
            "template_id": "tpl_del",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "title": "Nuevo borrador",
        },
    )
    alive = db.execute(
        "SELECT instance_id FROM main.admin_report_instances WHERE instance_id = 'rpt_del_2' AND active = true"
    ).fetchone()
    assert alive is not None


def test_create_allows_multiple_instances_same_template(tmp_path: Path) -> None:
    db = duckdb.connect(str(tmp_path / "hub_multi.duckdb"))
    run_pending_migrations(db)
    schema = [{"id": "body", "label": "Body"}]
    dispatch_command(
        db,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_m",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
            "name": "M",
            "template_uri": "/vault/m.docx",
            "section_schema": schema,
            "analyzer_mode": "jinja",
        },
    )
    for iid, title in (("rpt_1", "Uno"), ("rpt_2", "Dos")):
        dispatch_command(
            db,
            {
                "command_type": "create_report_instance",
                "instance_id": iid,
                "template_id": "tpl_m",
                "tenant_id": "default",
                "actor_email": "a@ex.com",
                "title": title,
            },
        )
    n = db.execute(
        "SELECT count(*) FROM main.admin_report_instances WHERE template_id = 'tpl_m' AND active = true"
    ).fetchone()
    assert n is not None and int(n[0]) == 2


def test_upsert_report_template_blocks_other_owner(tmp_path: Path) -> None:
    import pytest

    db = duckdb.connect(str(tmp_path / "hub_owner.duckdb"))
    run_pending_migrations(db)
    dispatch_command(
        db,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_own",
            "tenant_id": "default",
            "actor_email": "owner@ex.com",
            "name": "Mine",
            "template_uri": "/vault/m.docx",
            "section_schema": [{"id": "body"}],
            "analyzer_mode": "jinja",
        },
    )
    with pytest.raises(ValueError, match="otro propietario"):
        dispatch_command(
            db,
            {
                "command_type": "upsert_report_template",
                "template_id": "tpl_own",
                "tenant_id": "default",
                "actor_email": "other@ex.com",
                "name": "Hijack",
                "template_uri": "/vault/h.docx",
                "section_schema": [{"id": "body"}],
                "analyzer_mode": "jinja",
            },
        )


def test_preview_html_renders_sections() -> None:
    state = init_state_from_schema([{"id": "a", "label": "Sección A"}])
    html = render_preview_html(title="T", period_key="2026-06", state=state, section_schema=[{"id": "a"}])
    assert "Sección A" in html
