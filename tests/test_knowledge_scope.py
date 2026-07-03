from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_normalize_knowledge_scope_defaults() -> None:
    from duckclaw.knowledge_scope import normalize_knowledge_scope

    assert normalize_knowledge_scope("", project_id="") == "platform"
    assert normalize_knowledge_scope("", project_id="prj_a") == "both"
    assert normalize_knowledge_scope("project", project_id="") == "platform"
    assert normalize_knowledge_scope("both", project_id="prj_a") == "both"
    assert normalize_knowledge_scope("project", project_id="prj_a") == "project"


def test_build_knowledge_scope_clauses_platform_only() -> None:
    from duckclaw.knowledge_scope import build_knowledge_scope_clauses

    clauses, params = build_knowledge_scope_clauses(
        knowledge_scope="platform",
        project_id="",
    )
    assert "s.project_id = ''" in " ".join(clauses)
    assert params == []


@pytest.fixture
def hub_with_framework_knowledge(tmp_path: Path):
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.admin_knowledge_sources
          (source_id, tenant_id, project_id, worker_uid, source_kind, source_uri, status)
        VALUES ('ksrc_fw', 'tenant_a', '', '', 'folder', '/framework', 'ready')
        """
    )
    con.execute(
        """
        UPDATE main.admin_knowledge_sources
        SET display_name = 'Framework Docs'
        WHERE source_id = 'ksrc_fw'
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_documents
          (document_id, source_id, relative_path, title, checksum)
        VALUES ('kdoc_fw', 'ksrc_fw', 'guides/rag.md', 'RAG', 'sha256:fw')
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_chunks
          (chunk_id, document_id, source_id, tenant_id, project_id, worker_uid,
           chunk_index, content, content_hash, embedding_status)
        VALUES
          ('kchk_fw', 'kdoc_fw', 'ksrc_fw', 'tenant_a', '', '',
           0, 'Framework knowledge about RAG pipelines', 'hfw', 'PENDING')
        """
    )
    con.close()
    return db_path


def test_search_project_knowledge_platform_scope_without_project(
    hub_with_framework_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_scope,
        set_knowledge_tool_tenant_id,
    )
    from duckclaw.forge.skills.search_project_knowledge_bridge import search_project_knowledge

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_framework_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("")
    set_knowledge_tool_scope("platform")

    payload = json.loads(search_project_knowledge("RAG pipelines"))
    assert "error" not in payload
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["relative_path"] == "guides/rag.md"


def test_list_project_knowledge_platform_scope(
    hub_with_framework_knowledge: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        set_knowledge_tool_project_id,
        set_knowledge_tool_scope,
        set_knowledge_tool_tenant_id,
    )
    from duckclaw.forge.skills.list_project_knowledge_bridge import list_project_knowledge

    monkeypatch.setattr(
        "duckclaw.forge.skills.search_project_knowledge_bridge._resolve_hub_db_path",
        lambda: str(hub_with_framework_knowledge),
    )
    set_knowledge_tool_tenant_id("tenant_a")
    set_knowledge_tool_project_id("")
    set_knowledge_tool_scope("platform")

    payload = json.loads(list_project_knowledge())
    assert payload["knowledge_scope"] == "platform"
    assert payload["document_count"] == 1
