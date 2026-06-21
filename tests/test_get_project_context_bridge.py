"""Tests for get_project_context skill bridge."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from duckclaw.forge.skills.get_project_context_bridge import get_project_context


@patch("duckclaw.admin_knowledge_read.list_knowledge_sources")
@patch("duckclaw.forge.skills.get_project_context_bridge._open_hub_db")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_worker_uid")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_tenant_id")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_project_id")
def test_get_project_context_with_project(
    mock_project_id: MagicMock,
    mock_tenant_id: MagicMock,
    mock_worker_uid: MagicMock,
    mock_open_db: MagicMock,
    mock_list_sources: MagicMock,
) -> None:
    mock_project_id.return_value = "proj-abc"
    mock_tenant_id.return_value = "tenant-1"
    mock_worker_uid.return_value = "worker-x"
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = ("Demo", "active")
    mock_open_db.return_value = db
    mock_list_sources.return_value = [
        {
            "display_name": "docs",
            "source_kind": "folder",
            "status": "ready",
            "document_count": 3,
            "chunk_count": 42,
        }
    ]

    payload = json.loads(get_project_context())

    assert payload["project_id"] == "proj-abc"
    assert payload["project_name"] == "Demo"
    assert payload["chunk_count"] == 42
    assert payload["source_count"] == 1
    db.close.assert_called_once()


@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_worker_uid")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_tenant_id")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_project_id")
def test_get_project_context_no_project(
    mock_project_id: MagicMock,
    mock_tenant_id: MagicMock,
    mock_worker_uid: MagicMock,
) -> None:
    mock_project_id.return_value = ""
    mock_tenant_id.return_value = "tenant-1"
    mock_worker_uid.return_value = ""

    payload = json.loads(get_project_context())

    assert payload["project_id"] == ""
    assert "warning" in payload
    assert payload["chunk_count"] == 0
