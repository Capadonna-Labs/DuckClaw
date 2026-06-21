"""Tests for export_output_document skill bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.forge.skills.convert_document_bridge import convert_document


def test_export_output_document_docx(tmp_path, monkeypatch) -> None:
    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))

    md = out_root / "informe.md"
    md.write_text("# Informe\n\nContenido.", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_bytes(b"PK fake docx")
        return MagicMock(returncode=0, stderr="", stdout="")

    with patch("duckclaw.document_toolbox.convert.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("duckclaw.document_toolbox.convert.subprocess.run", side_effect=fake_run):
            raw = convert_document("informe.md", output_format="docx")

    payload = json.loads(raw)
    assert payload["format"] == "docx"
    assert Path(payload["path"]).suffix == ".docx"


def test_export_output_document_missing_source(tmp_path, monkeypatch) -> None:
    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))

    with patch("duckclaw.document_toolbox.convert.shutil.which", return_value="/usr/bin/pandoc"):
        raw = convert_document("missing.md", output_format="pdf")

    payload = json.loads(raw)
    assert "error" in payload


def test_export_output_document_pdf_without_engine(tmp_path, monkeypatch) -> None:
    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    md = out_root / "doc.md"
    md.write_text("# Test", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "pandoc":
            return "/usr/bin/pandoc"
        return None

    with patch("duckclaw.document_toolbox.convert.shutil.which", side_effect=fake_which):
        raw = convert_document("doc.md", output_format="pdf")

    payload = json.loads(raw)
    assert "error" in payload
    assert "pdflatex" in payload["error"] or "PDF" in payload["error"]


def test_export_output_document_pandoc_failure(tmp_path, monkeypatch) -> None:
    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    md = out_root / "doc.md"
    md.write_text("# Test", encoding="utf-8")

    mock_run = MagicMock(return_value=MagicMock(returncode=1, stderr="conversion failed", stdout=""))
    with patch("duckclaw.document_toolbox.convert.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("duckclaw.document_toolbox.convert.subprocess.run", mock_run):
            raw = convert_document("doc.md", output_format="docx")

    payload = json.loads(raw)
    assert payload["error"].startswith("pandoc falló")
