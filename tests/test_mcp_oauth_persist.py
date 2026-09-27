"""OAuth token persistence must go through DB-Writer, not a Gateway write handle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from duckclaw.mcp_connector_oauth import persist_mcp_connector_oauth_tokens
from duckclaw.write_commands import SetMcpConnectorAuthCommand


def test_persist_oauth_tokens_enqueues_set_mcp_connector_auth() -> None:
    with patch(
        "duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"
    ), patch(
        "duckclaw.gateway_enqueue.enqueue_admin_command", return_value="task-oauth-1"
    ) as enqueue:
        task_id = persist_mcp_connector_oauth_tokens(
            tenant_id="tenant-a",
            actor_email="user@example.com",
            connector_id="mcp_notion",
            bearer_token="access-1",
            refresh_token="refresh-1",
            oauth_client_id="dcr-client",
            oauth_redirect_uri="https://example.test/callback",
        )
    assert task_id == "task-oauth-1"
    enqueue.assert_called_once()
    cmd = enqueue.call_args.args[0]
    assert isinstance(cmd, SetMcpConnectorAuthCommand)
    assert cmd.connector_id == "mcp_notion"
    assert cmd.bearer_token == "access-1"
    assert cmd.refresh_token == "refresh-1"
    assert cmd.oauth_client_id == "dcr-client"
    assert cmd.oauth_redirect_uri == "https://example.test/callback"


def test_persist_oauth_tokens_falls_back_to_sync_when_enqueue_fails() -> None:
    db = MagicMock()
    with patch(
        "duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"
    ), patch(
        "duckclaw.gateway_enqueue.enqueue_admin_command",
        side_effect=RuntimeError("redis down"),
    ), patch("duckclaw.DuckClaw", return_value=db), patch(
        "duckclaw.write_handlers.mcp_connectors._apply_set_mcp_connector_auth",
    ) as apply:
        task_id = persist_mcp_connector_oauth_tokens(
            tenant_id="tenant-a",
            actor_email="user@example.com",
            connector_id="mcp_google_gmail",
            bearer_token="access-1",
            refresh_token="refresh-1",
        )
    assert task_id  # sync fallback still returns the command task_id
    apply.assert_called_once()
    db.close.assert_called_once()


def test_persist_oauth_tokens_raises_when_enqueue_and_sync_fail() -> None:
    with patch(
        "duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"
    ), patch(
        "duckclaw.gateway_enqueue.enqueue_admin_command",
        side_effect=RuntimeError("redis down"),
    ), patch(
        "duckclaw.DuckClaw",
        side_effect=OSError(
            "Can't open a connection to same database file with a different configuration"
        ),
    ):
        with pytest.raises(RuntimeError, match="No se pudo guardar el token OAuth"):
            persist_mcp_connector_oauth_tokens(
                tenant_id="tenant-a",
                actor_email="user@example.com",
                connector_id="mcp_notion",
                bearer_token="access-1",
                refresh_token="refresh-1",
            )
