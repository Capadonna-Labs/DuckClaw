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


def test_analyze_plain_docx_gets_default_sections(tmp_path: Path) -> None:
    from docx import Document

    target = tmp_path / "informe_libre.docx"
    doc = Document()
    doc.add_paragraph("Informe mensual de gestión sin placeholders Jinja.")
    doc.save(str(target))
    analysis = analyze_docx_template(target)
    assert analysis["analyzer_mode"] == "mixed"
    assert len(analysis["sections"]) >= 5
    assert analysis.get("warning")


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


def test_preview_html_renders_sections() -> None:
    state = init_state_from_schema([{"id": "a", "label": "Sección A"}])
    html = render_preview_html(title="T", period_key="2026-06", state=state, section_schema=[{"id": "a"}])
    assert "Sección A" in html
