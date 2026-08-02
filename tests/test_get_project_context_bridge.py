"""Tests for get_project_context skill bridge."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from duckclaw.forge.skills.get_project_context_bridge import get_project_context


@patch("duckclaw.forge.skills.get_project_context_bridge._disk_allowed_roots_preview", return_value=[])
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
    _mock_disk: MagicMock,
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
    assert "lanes" in payload
    assert "disk_allowed_roots" in payload
    db.close.assert_called_once()


@patch("duckclaw.forge.skills.get_project_context_bridge._disk_allowed_roots_preview")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_scope", return_value="platform")
@patch("duckclaw.admin_knowledge_read.list_knowledge_sources", return_value=[])
@patch("duckclaw.forge.skills.get_project_context_bridge._open_hub_db")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_worker_uid")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_tenant_id")
@patch("duckclaw.forge.skills.knowledge_tool_context.get_knowledge_tool_project_id")
def test_get_project_context_reports_disk_roots_when_no_indexed_sources(
    mock_project_id: MagicMock,
    mock_tenant_id: MagicMock,
    mock_worker_uid: MagicMock,
    mock_open_db: MagicMock,
    _mock_list: MagicMock,
    _mock_scope: MagicMock,
    mock_disk: MagicMock,
) -> None:
    mock_project_id.return_value = ""
    mock_tenant_id.return_value = "tenant-1"
    mock_worker_uid.return_value = ""
    mock_open_db.return_value = MagicMock()
    mock_disk.return_value = [
        {
            "label": "Developer",
            "path": "/Users/workstation/Developer",
            "exists": True,
            "in_chat": False,
            "note": "Solo disco",
        }
    ]

    payload = json.loads(get_project_context())

    assert payload["chunk_count"] == 0
    assert payload["disk_allowed_roots"][0]["label"] == "Developer"
    assert "disk_allowed_roots" in payload["warning"]
