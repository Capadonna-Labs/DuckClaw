from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_knowledge_hub(con) -> None:
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


@pytest.fixture(autouse=True)
def _reset_knowledge_tool_context() -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_scope,
        set_knowledge_tool_tenant_id,
        set_knowledge_tool_worker_uid,
    )

    set_knowledge_tool_tenant_id("default")
    set_knowledge_tool_project_id("")
    set_knowledge_tool_scope("")
    set_knowledge_tool_worker_uid("")


@pytest.fixture
def hub_with_knowledge(tmp_path: Path):
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    run_pending_migrations(con)
    _seed_knowledge_hub(con)
    con.close()
    return db_path


def test_search_project_knowledge_returns_chunks_when_context_set(
    hub_with_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_tenant_id,
        set_knowledge_tool_worker_uid,
    )
    from duckclaw.forge.skills.search_project_knowledge_bridge import search_project_knowledge

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("proj_a")
    set_knowledge_tool_worker_uid("wrk_a")

    payload = json.loads(search_project_knowledge("least privilege"))
    assert "error" not in payload
    assert len(payload["chunks"]) == 1
    chunk = payload["chunks"][0]
    assert chunk["relative_path"] == "aws/iam.md"
    assert chunk["chunk_index"] == 0
    assert "least privilege" in chunk["excerpt"].lower()


def test_list_project_knowledge_returns_document_inventory(
    hub_with_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_tenant_id,
    )
    from duckclaw.forge.skills.list_project_knowledge_bridge import list_project_knowledge

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("proj_a")

    payload = json.loads(list_project_knowledge())
    assert payload["document_count"] == 1
    assert payload["documents"][0]["relative_path"] == "aws/iam.md"


def test_read_knowledge_document_matches_path_substring(
    hub_with_knowledge: Path,
) -> None:
    import duckdb

    from duckclaw.forge.rag.knowledge_core import read_knowledge_document

    con = duckdb.connect(str(hub_with_knowledge), read_only=True)
    try:
        rows = read_knowledge_document(
            con,
            relative_path="iam.md",
            tenant_id="tenant_a",
            project_id="proj_a",
        )
    finally:
        con.close()
    assert len(rows) == 1
    assert rows[0]["relative_path"] == "aws/iam.md"


def test_fold_search_text_strips_accents() -> None:
    from duckclaw.forge.rag.knowledge_core import fold_search_text

    assert fold_search_text("Caché") == "cache"


def test_read_project_knowledge_returns_content(
    hub_with_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_tenant_id,
    )
    from duckclaw.forge.skills.read_project_knowledge_bridge import read_project_knowledge

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("proj_a")

    payload = json.loads(read_project_knowledge("aws/iam.md"))
    assert payload["relative_path"] == "aws/iam.md"
    assert "least privilege" in payload["content"].lower()


def test_get_project_context_includes_knowledge_scope(
    hub_with_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_scope,
        set_knowledge_tool_tenant_id,
    )
    from duckclaw.forge.skills.get_project_context_bridge import get_project_context

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("proj_a")
    set_knowledge_tool_scope("both")
    payload = json.loads(get_project_context())
    assert payload["knowledge_scope"] == "both"
    assert payload["document_count"] == 1
