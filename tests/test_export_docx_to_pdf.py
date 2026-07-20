"""Tests for export_docx_to_pdf (LibreOffice Word→PDF)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from duckclaw.document_toolbox.export_pdf import export_docx_to_pdf_file


def test_export_rejects_non_docx(tmp_path: Path) -> None:
    src = tmp_path / "note.md"
    src.write_text("x", encoding="utf-8")
    try:
        export_docx_to_pdf_file(source=src)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert ".docx" in str(exc)


@patch("duckclaw.document_toolbox.export_pdf.subprocess.run")
def test_export_moves_pdf_to_target(mock_run: MagicMock, tmp_path: Path) -> None:
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK")
    dest = tmp_path / "out" / "final.pdf"

    def fake_run(cmd, **kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "a.pdf").write_bytes(b"%PDF")
        return MagicMock(returncode=0, stderr="", stdout="")

    mock_run.side_effect = fake_run
    with patch(
        "duckclaw.document_toolbox.export_pdf.libreoffice_binary",
        return_value="/bin/soffice",
    ):
        payload = export_docx_to_pdf_file(source=src, target=dest)

    assert dest.is_file()
    assert payload["path"] == str(dest.resolve())


def test_bridge_missing_libreoffice(tmp_path: Path, monkeypatch) -> None:
    from duckclaw.forge.skills.export_docx_to_pdf_bridge import export_docx_to_pdf

    docx = tmp_path / "x.docx"
    docx.write_bytes(b"PK")
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(tmp_path))

    with patch(
        "duckclaw.forge.skills.export_docx_to_pdf_bridge.export_docx_to_pdf_file",
        side_effect=ValueError("LibreOffice no está instalado"),
    ), patch(
        "duckclaw.forge.skills.export_docx_to_pdf_bridge.libreoffice_available",
        return_value=False,
    ):
        raw = export_docx_to_pdf(docx_path=str(docx))

    payload = json.loads(raw)
    assert "error" in payload
    assert "hint" in payload
