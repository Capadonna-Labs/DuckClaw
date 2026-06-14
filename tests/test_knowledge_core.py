from __future__ import annotations

import pytest


def test_safe_relative_path_rejects_escape_and_hidden(tmp_path) -> None:
    from duckclaw.forge.rag.knowledge_core import safe_relative_path

    root = tmp_path / "docs"
    root.mkdir()
    good = root / "aws" / "iam.md"
    good.parent.mkdir()
    good.write_text("# IAM\nLeast privilege", encoding="utf-8")

    assert safe_relative_path(root, good) == "aws/iam.md"

    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        safe_relative_path(root, outside)

    hidden = root / ".env"
    hidden.write_text("TOKEN=x", encoding="utf-8")
    with pytest.raises(ValueError, match="hidden"):
        safe_relative_path(root, hidden)


def test_chunk_text_prefers_markdown_sections() -> None:
    from duckclaw.forge.rag.knowledge_core import chunk_text

    text = "# Root\nIntro\n\n## IAM\nUse least privilege.\n\n## CloudTrail\nAudit events."
    chunks = chunk_text(text, max_chars=40, overlap_chars=0)

    assert chunks
    assert any("## IAM" in c for c in chunks)
    assert any("CloudTrail" in c for c in chunks)


def test_build_document_payload_is_deterministic(tmp_path) -> None:
    from duckclaw.forge.rag.knowledge_core import build_document_payload

    root = tmp_path / "docs"
    root.mkdir()
    doc = root / "aws.md"
    doc.write_text("# AWS\nIAM and CloudTrail", encoding="utf-8")

    first = build_document_payload(root=root, path=doc, source_id="ksrc_test")
    second = build_document_payload(root=root, path=doc, source_id="ksrc_test")

    assert first.document["document_id"] == second.document["document_id"]
    assert first.document["checksum"] == second.document["checksum"]
    assert first.chunks[0]["chunk_id"] == second.chunks[0]["chunk_id"]
    assert first.chunks[0]["embedding_status"] == "PENDING"


def test_build_uploaded_document_payload_preserves_safe_relative_path() -> None:
    from duckclaw.forge.rag.knowledge_core import build_uploaded_document_payload

    payload = build_uploaded_document_payload(
        filename="aws/iam.md",
        data=b"# IAM\n\nLeast privilege",
        source_id="ksrc_upload",
    )

    assert payload.document["relative_path"] == "aws/iam.md"
    assert payload.document["mime_type"] == "text/markdown"
    assert payload.chunks[0]["metadata"]["upload"] is True

    with pytest.raises(ValueError, match="secret"):
        build_uploaded_document_payload(filename=".env", data=b"TOKEN=x", source_id="ksrc_upload")


def test_search_knowledge_lexical_filters_scope(db_with_knowledge) -> None:
    from duckclaw.forge.rag.knowledge_core import search_knowledge

    con = db_with_knowledge
    rows = search_knowledge(
        con,
        query="least privilege",
        tenant_id="tenant_a",
        project_id="proj_a",
        worker_uid="wrk_a",
        limit=5,
        embedding_fn=lambda _: None,
    )

    assert len(rows) == 1
    assert rows[0]["relative_path"] == "aws/iam.md"
    assert "least privilege" in rows[0]["text"].lower()


def test_knowledge_context_provider_builds_inventory_and_blocks(db_with_knowledge) -> None:
    from duckclaw.forge.rag.context_provider import build_knowledge_context

    context = build_knowledge_context(
        db_with_knowledge,
        query="Que base de conocimiento tienes",
        tenant_id="tenant_a",
        project_id="proj_a",
        worker_uid="wrk_a",
        embedding_fn=lambda _: None,
    )

    assert context.inventory
    assert context.inventory[0]["display_name"] == "AWS IAM"
    assert "RAG_SOURCE_INVENTORY" in context.inventory_block
    assert "No confundas la base de conocimiento RAG con la bóveda DuckDB" in context.guidance_line


@pytest.fixture
def db_with_knowledge():
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.admin_knowledge_sources
          (source_id, tenant_id, project_id, worker_uid, source_kind, source_uri, status)
        VALUES ('ksrc_a', 'tenant_a', 'proj_a', 'wrk_a', 'folder', '/docs', 'ready')
        """
    )
    con.execute(
        """
        UPDATE main.admin_knowledge_sources
        SET display_name = 'AWS IAM'
        WHERE source_id = 'ksrc_a'
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_documents
          (document_id, source_id, relative_path, title, checksum)
        VALUES ('kdoc_a', 'ksrc_a', 'aws/iam.md', 'IAM', 'sha256:a')
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_chunks
          (chunk_id, document_id, source_id, tenant_id, project_id, worker_uid,
           chunk_index, content, content_hash, embedding_status)
        VALUES
          ('kchk_a', 'kdoc_a', 'ksrc_a', 'tenant_a', 'proj_a', 'wrk_a',
           0, 'IAM least privilege policies', 'h1', 'PENDING'),
          ('kchk_b', 'kdoc_a', 'ksrc_a', 'tenant_a', 'other', 'wrk_a',
           1, 'Do not leak to other project', 'h2', 'PENDING')
        """
    )
    yield con
    con.close()
