"""OAuth token persistence must not rely on async queue alone."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from duckclaw.mcp_connector_oauth import persist_mcp_connector_oauth_tokens


def test_persist_oauth_tokens_writes_sync() -> None:
    db = MagicMock()
    db.execute.return_value = [("set_abc",)]  # DuckClaw.execute returns fetchall list
    with patch("duckclaw.DuckClaw", return_value=db):
        with patch(
            "duckclaw.write_handlers.mcp_connectors._apply_set_mcp_connector_auth",
        ) as apply:
            with patch("duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"):
                task_id = persist_mcp_connector_oauth_tokens(
                    tenant_id="tenant-a",
                    actor_email="user@example.com",
                    connector_id="mcp_google_gmail",
                    bearer_token="access-1",
                    refresh_token="refresh-1",
                )
    assert task_id == ""
    apply.assert_called_once()
    db.close.assert_called_once()


def test_persist_oauth_tokens_raises_when_hub_locked() -> None:
    with patch("duckclaw.DuckClaw", side_effect=OSError("Could not set lock on file")):
        with patch("duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"):
            with pytest.raises(RuntimeError, match="No se pudo guardar el token OAuth"):
                persist_mcp_connector_oauth_tokens(
                    tenant_id="tenant-a",
                    actor_email="user@example.com",
                    connector_id="mcp_google_gmail",
                    bearer_token="access-1",
                    refresh_token="refresh-1",
                )
