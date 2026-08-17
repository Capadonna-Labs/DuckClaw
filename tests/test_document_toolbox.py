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


@patch("duckclaw.document_toolbox.export_pdf.subprocess.run")
def test_export_docx_to_pdf_file(mock_run: MagicMock, tmp_path: Path) -> None:
    from duckclaw.document_toolbox.export_pdf import export_docx_to_pdf_file

    src = tmp_path / "informe.docx"
    src.write_bytes(b"PK\x03\x04fake")

    def fake_run(cmd, **kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "informe.pdf").write_bytes(b"%PDF-1.4")
        return MagicMock(returncode=0, stderr="", stdout="")

    mock_run.side_effect = fake_run
    with patch(
        "duckclaw.document_toolbox.export_pdf.libreoffice_binary",
        return_value="/usr/bin/soffice",
    ):
        payload = export_docx_to_pdf_file(source=src)

    assert payload["format"] == "pdf"
    assert Path(payload["path"]).is_file()
    assert payload["engine"] == "libreoffice"


def test_baseline_includes_export_pdf() -> None:
    pack = load_document_toolbox()
    assert "export_docx_to_pdf" in pack["baseline_tools"]
    assert "list_report_instances" in pack["baseline_tools"]


def test_extract_native_md_without_markitdown(tmp_path: Path) -> None:
    from duckclaw.document_toolbox.extract import convert_file_path_to_text

    md = tmp_path / "note.md"
    md.write_text("# Título", encoding="utf-8")
    assert convert_file_path_to_text(md) == "# Título"


def test_xlsx_fallback_when_magika_models_missing(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    from duckclaw.document_toolbox import extract as extract_mod

    xlsx = tmp_path / "movimientos.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Contabilidad"
    ws.append(["Fecha", "Monto"])
    ws.append(["2026-01-01", 1500])
    wb.save(xlsx)

    class _Boom:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "model dir not found at C:\\Temp\\_MEI123\\magika\\models\\standard_v3_3"
            )

    with patch.object(extract_mod, "markitdown_available", return_value=True), patch.dict(
        "sys.modules",
        {"markitdown": MagicMock(MarkItDown=_Boom, StreamInfo=MagicMock)},
    ):
        # Force import path inside _convert_path to use our boom MarkItDown
        import sys

        fake = MagicMock()
        fake.MarkItDown = _Boom
        fake.StreamInfo = MagicMock(return_value=None)
        sys.modules["markitdown"] = fake
        text = extract_mod.convert_bytes_to_text(
            data=xlsx.read_bytes(),
            filename="2026 MOVIMIENTOS CONTABILIDAD.xlsx",
        )
    assert "Contabilidad" in text or "Fecha" in text
    assert "1500" in text


def test_convert_file_path_leaves_original_bytes_intact(tmp_path: Path) -> None:
    """Binary extract must copy first; the user's original file must not change."""
    pytest.importorskip("openpyxl")
    import hashlib

    from openpyxl import Workbook

    from duckclaw.document_toolbox.extract import convert_file_path_to_text

    xlsx = tmp_path / "original.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Datos"
    ws.append(["A", "B"])
    ws.append([1, 2])
    wb.save(xlsx)
    before = hashlib.sha256(xlsx.read_bytes()).hexdigest()
    before_mtime = xlsx.stat().st_mtime_ns

    text = convert_file_path_to_text(xlsx)
    assert "Datos" in text or "A" in text
    assert hashlib.sha256(xlsx.read_bytes()).hexdigest() == before
    assert xlsx.stat().st_mtime_ns == before_mtime


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
