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


def test_search_project_knowledge_requires_project_id() -> None:
    from duckclaw.forge.skills.knowledge_tool_context import set_knowledge_tool_project_id
    from duckclaw.forge.skills.search_project_knowledge_bridge import search_project_knowledge

    set_knowledge_tool_project_id("")
    payload = json.loads(search_project_knowledge("anything"))
    assert "error" in payload
    assert "project_id" in payload["error"].lower()
