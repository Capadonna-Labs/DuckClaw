"""Tests for duckclaw.document_toolbox core."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.document_toolbox.pack import load_document_toolbox
from duckclaw.document_toolbox.registry import (
    AUTHOR_TEXT_SUFFIXES,
    EXTRACT_SUFFIXES,
    INGEST_NATIVE_SUFFIXES,
    assert_author_text_path,
    ingest_lane_for_suffix,
)


def test_load_document_toolbox_pack() -> None:
    pack = load_document_toolbox()
    assert pack["pack_version"] == "document_toolbox_v1"
    tools = pack["baseline_tools"]
    assert "extract_document_text" in tools
    assert "render_docx_template" in tools
    assert "convert_document" not in tools
    assert "render_report_instance" in tools


def test_ingest_lanes() -> None:
    assert ingest_lane_for_suffix(".pdf") == "extract"
    assert ingest_lane_for_suffix(".md") == "ingest_native"
    assert ingest_lane_for_suffix(".xyz") == "unsupported"


def test_author_text_allowlist() -> None:
    assert ".md" in AUTHOR_TEXT_SUFFIXES
    assert ".py" in AUTHOR_TEXT_SUFFIXES
    assert_author_text_path("notes/ok.md")
    with pytest.raises(ValueError, match="binarios"):
        assert_author_text_path("informe.docx")
    with pytest.raises(ValueError, match="no permitida"):
        assert_author_text_path("foto.bmp")


def test_corporate_template_seed_exists() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "packages/shared/src/duckclaw/seeds/document_templates/corporate_report.docx"
    )
    assert path.is_file()
    assert path.stat().st_size > 100


@patch("duckclaw.document_toolbox.convert.subprocess.run")
def test_convert_document_file_docx(mock_run: MagicMock, tmp_path: Path) -> None:
    from duckclaw.document_toolbox.convert import convert_document_file

    mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
    src = tmp_path / "informe.md"
    src.write_text("# Hola", encoding="utf-8")
    out = tmp_path / "informe.docx"

    def fake_run(cmd, **kwargs):
        out.write_bytes(b"PK")
        return MagicMock(returncode=0, stderr="", stdout="")

    mock_run.side_effect = fake_run
    with patch("duckclaw.document_toolbox.convert.shutil.which", return_value="/usr/bin/pandoc"):
        payload = convert_document_file(source=src, output_format="docx", target=out)

    assert payload["format"] == "docx"
    assert out.is_file()


def test_extract_native_md_without_markitdown(tmp_path: Path) -> None:
    from duckclaw.document_toolbox.extract import convert_file_path_to_text

    md = tmp_path / "note.md"
    md.write_text("# Título", encoding="utf-8")
    assert convert_file_path_to_text(md) == "# Título"


def test_render_docx_template_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("docxtpl")
    from duckclaw.document_toolbox.templates import render_docx_template

    template = (
        Path(__file__).resolve().parents[1]
        / "packages/shared/src/duckclaw/seeds/document_templates/corporate_report.docx"
    )
    out = tmp_path / "out.docx"
    payload = render_docx_template(
        template_id="corporate_report",
        context={
            "title": "Informe Q1",
            "subtitle": "Resumen ejecutivo",
            "author": "Samuel",
            "tenant_name": "Acme",
            "date": "2026-06-21",
            "body": "Contenido del informe.",
        },
        output_path=out,
    )
    assert payload["format"] == "docx"
    assert out.stat().st_size > 100
