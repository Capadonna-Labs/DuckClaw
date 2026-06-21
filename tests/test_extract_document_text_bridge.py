"""Tests for extract_document_text skill bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from duckclaw.forge.skills.extract_document_text_bridge import extract_document_text


def test_extract_document_text_native_md(tmp_path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    doc = vault / "nota.md"
    doc.write_text("# Hola mundo", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(vault))

    payload = json.loads(extract_document_text("nota.md"))
    assert "error" not in payload
    assert "Hola mundo" in payload["text"]


@patch("duckclaw.forge.skills.extract_document_text_bridge.extract_document_text_from_path")
def test_extract_document_text_pdf(mock_extract, tmp_path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    pdf = vault / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(vault))
    mock_extract.return_value = ("Texto extraído", "text/plain")

    payload = json.loads(extract_document_text("doc.pdf"))
    assert payload["text"] == "Texto extraído"
