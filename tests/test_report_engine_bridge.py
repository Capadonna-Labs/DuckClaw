"""Report Engine bridge — escrituras sincronizadas y políticas de tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.forge.skills.report_engine_bridge import register_report_template


def test_register_report_template_surfaces_db_writer_failure(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from docx import Document

    docx_path = tmp_path / "informe.docx"
    doc = Document()
    doc.add_paragraph("Informe mensual")
    doc.save(str(docx_path))

    monkeypatch.setattr(
        "duckclaw.forge.rag.knowledge_paths.resolve_readable_document_path",
        lambda **_: docx_path,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._hub_db_path",
        lambda: str(tmp_path / "hub.duckdb"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._session_scope",
        lambda: ("default", "user@example.com", "proj-1"),
    )

    with patch(
        "duckclaw.db_write_queue.enqueue_or_apply_duckdb_write_sync",
        return_value="task-abc",
    ):
        with patch("duckclaw.spawn_profile.spawn_inline_writes_enabled", return_value=False):
            with patch(
                "duckclaw.db_write_queue.poll_task_status_sync",
                return_value=MagicMock(status="failed", detail="ACL denegado"),
            ):
                raw = register_report_template(
                    "INFORME MENSUAL.docx",
                    "Informe mensual",
                )
    payload = json.loads(raw)
    assert "error" in payload
    assert "ACL denegado" in payload["error"]


def test_framework_pack_includes_report_engine_guidance() -> None:
    from duckclaw.framework_policy_pack import get_framework_policy_content

    content = get_framework_policy_content("system_prompt", "default")
    assert content
    assert "REPORT ENGINE" in content
    assert "render_report_instance" in content
    assert "generate_report_docx_from_markdown" in content
    assert "render_docx_template" in content
    assert "pandoc" in content.lower()


def test_generate_report_docx_discovers_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.report_engine_bridge import _discover_markdown_relative_path

    out_root = tmp_path / "vault"
    informes = out_root / "Informes"
    informes.mkdir(parents=True)
    target = informes / "INFORME MENSUAL N°4 - JUNIO 2026.md"
    target.write_text("# Informe", encoding="utf-8")
    other = informes / "borrador.md"
    other.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "duckclaw.forge.rag.knowledge_paths.knowledge_output_roots",
        lambda: [out_root],
    )

    rel = _discover_markdown_relative_path(report_title="INFORME MENSUAL N°4 - JUNIO 2026")
    assert rel == "Informes/INFORME MENSUAL N°4 - JUNIO 2026.md"


def test_generate_report_docx_from_markdown_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.report_engine_bridge import generate_report_docx_from_markdown

    calls: list[str] = []

    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._resolve_registered_template_id",
        lambda **_: ("rtpl_existing", [{"id": "resumen_ejecutivo", "label": "Resumen"}]),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._read_markdown_for_report",
        lambda **_: ("# Informe\n\nContenido mensual", "Informes/informe.md"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge.create_report_instance",
        lambda **_: json.dumps({"instance_id": "rpt_abc", "template_id": "rtpl_existing", "status": "draft"}),
    )

    def _patch(**kwargs: object) -> str:
        calls.append(str(kwargs.get("section_id")))
        return json.dumps({"status": "updated", "section_id": kwargs.get("section_id")})

    monkeypatch.setattr("duckclaw.forge.skills.report_engine_bridge.patch_report_section", _patch)
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge.render_report_instance",
        lambda iid: json.dumps(
            {"path": "/out/reports/rpt_abc.docx", "relative_path": "reports/rpt_abc.docx", "format": "docx"}
        ),
    )

    raw = generate_report_docx_from_markdown(
        template_docx_path="INFORME MENSUAL.docx",
        report_title="Informe N°4",
        markdown_relative_path="Informes/informe.md",
        period_key="2026-06",
    )
    payload = json.loads(raw)
    assert payload["instance_id"] == "rpt_abc"
    assert payload["relative_path"] == "reports/rpt_abc.docx"
    assert calls == ["resumen_ejecutivo"]
