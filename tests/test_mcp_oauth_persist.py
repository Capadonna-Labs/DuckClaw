"""OAuth token persistence goes through DB-Writer and survives until it lands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.mcp_connector_oauth import persist_mcp_connector_oauth_tokens


def test_persist_oauth_tokens_enqueues_typed_command() -> None:
    # Gateway must never open the hub RW (it raced DB-Writer: "Conflict on tuple deletion").
    with patch("duckclaw.db_write_queue.enqueue_typed_command", return_value="task-1") as enq:
        with patch("duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"):
            task_id = persist_mcp_connector_oauth_tokens(
                tenant_id="tenant-a",
                actor_email="user@example.com",
                connector_id="mcp_google_gmail",
                bearer_token="access-1",
                refresh_token="refresh-1",
                oauth_client_id="client-1",
            )
    assert task_id == "task-1"
    cmd = enq.call_args.args[0]
    assert cmd.command_type == "set_mcp_connector_auth"
    assert (cmd.bearer_token, cmd.refresh_token, cmd.oauth_client_id) == ("access-1", "refresh-1", "client-1")
    assert enq.call_args.kwargs["db_path"] == "/tmp/hub.duckdb"


def test_persist_oauth_tokens_raises_when_enqueue_fails() -> None:
    with patch("duckclaw.db_write_queue.enqueue_typed_command", side_effect=ConnectionError("redis down")):
        with patch("duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"):
            with pytest.raises(RuntimeError, match="No se pudo guardar el token OAuth"):
                persist_mcp_connector_oauth_tokens(
                    tenant_id="tenant-a",
                    actor_email="user@example.com",
                    connector_id="mcp_google_gmail",
                    bearer_token="access-1",
                    refresh_token="refresh-1",
                )


def test_rotated_refresh_token_is_reused_before_hub_write_lands() -> None:
    """Notion rotates refresh tokens: the next refresh must use the new one, not the hub's stale one."""
    from duckclaw.admin_mcp_connectors import _REFRESHED_OAUTH, resolve_connector_bearer_token

    connector = {
        "auth_kind": "bearer",
        "auth_secret_key": "mcp_notion.bearer",
        "tenant_id": "default",
        "owner_email": "admin@example.com",
        "connector_id": "mcp_notion",
        "preset_id": "notion",
    }
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    db = MagicMock()
    db._read_only = True

    def _setting(**kwargs):
        return {"value": {"mcp_notion.refresh": "hub-refresh", "notion.client_id": "c"}.get(kwargs.get("key"), "")}

    refreshes = iter(
        [
            {"access_token": "access-2", "refresh_token": "refresh-2"},
            {"access_token": "access-3", "refresh_token": "refresh-3"},
        ]
    )
    with patch("duckclaw.admin_mcp_connectors.resolve_runtime_setting", side_effect=lambda *a, **k: _setting(**k)):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            return_value={"value_text": "access-1", "updated_at": stale_ts},
        ):
            with patch(
                "duckclaw.mcp_notion_oauth.refresh_notion_access_token",
                side_effect=lambda *a, **k: next(refreshes),
            ) as mock_refresh:
                with patch("duckclaw.db_write_queue.enqueue_typed_command", return_value="t"):
                    with patch("duckclaw.gateway_db.get_gateway_db_path", return_value="/tmp/hub.duckdb"):
                        assert resolve_connector_bearer_token(db, connector) == "access-2"
                        # Within the window the cached access is served without refreshing again.
                        assert resolve_connector_bearer_token(db, connector) == "access-2"
                        assert mock_refresh.call_count == 1
                        # Window expired while the hub still holds the old pair.
                        a, r, _ = _REFRESHED_OAUTH[("default", "mcp_notion")]
                        _REFRESHED_OAUTH[("default", "mcp_notion")] = (a, r, 0.0)
                        assert resolve_connector_bearer_token(db, connector) == "access-3"
    # 1st refresh used the hub's token; the 2nd must use the rotated one, not the hub's again.
    assert mock_refresh.call_args_list[0].args[0] != "refresh-2"
    assert mock_refresh.call_args_list[1].args[0] == "refresh-2"
