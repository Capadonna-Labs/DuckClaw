from __future__ import annotations

from unittest.mock import patch


def test_knowledge_upload_defaults_compute_embeddings_true() -> None:
    src = open(
        "services/api-gateway/routers/admin_domains/knowledge.py",
        encoding="utf-8",
    ).read()
    assert "compute_embeddings: bool = Form(default=True)" in src
    assert "compute_embeddings: bool = True" in src


def test_normalize_uploaded_pdf_uses_markitdown() -> None:
    from duckclaw.forge.rag.knowledge_core import normalize_uploaded_document

    with patch(
        "duckclaw.forge.rag.markitdown_convert._convert_path",
        return_value="# Doc\n\nConverted PDF text.",
    ):
        rel, text, mime = normalize_uploaded_document("docs/report.pdf", b"%PDF-fake")

    assert rel == "docs/report.pdf"
    assert "Converted PDF" in text
    assert mime == "text/markdown"


def test_playground_rag_project_warning_component() -> None:
    from pathlib import Path

    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    warn = Path("apps/duckclaw-admin/src/components/playground/PlaygroundRagProjectWarning.tsx").read_text(
        encoding="utf-8"
    )
    assert "PlaygroundRagProjectWarning" in page
    assert "indexedKnowledgeSources" in page
    assert "Hay documentos indexados" in warn


def test_knowledge_page_semantic_search_toggle() -> None:
    from pathlib import Path

    page = Path("apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx").read_text(encoding="utf-8")
    assert "computeEmbeddings" in page
    assert "Búsqueda semántica" in page
    assert ".pdf" in page
