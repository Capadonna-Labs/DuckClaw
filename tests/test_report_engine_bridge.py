"""Report Engine bridge — escrituras sincronizadas y políticas de tools."""

from __future__ import annotations

import json
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
    assert "pandoc" in content.lower()
