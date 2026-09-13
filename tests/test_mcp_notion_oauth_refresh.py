"""Notion OAuth bearer resolution + refresh_token exchange."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token
from duckclaw.mcp_notion_oauth import refresh_notion_access_token


def _notion_connector() -> dict:
    return {
        "auth_kind": "bearer",
        "auth_secret_key": "mcp_notion.bearer",
        "tenant_id": "default",
        "owner_email": "admin@example.com",
        "connector_id": "mcp_notion",
        "preset_id": "notion",
    }


def test_refresh_notion_access_token_posts_refresh_grant() -> None:
    pr = MagicMock()
    pr.raise_for_status = MagicMock()
    pr.json.return_value = {"authorization_servers": ["https://auth.notion.test"]}

    meta = MagicMock()
    meta.raise_for_status = MagicMock()
    meta.json.return_value = {"token_endpoint": "https://auth.notion.test/token"}

    tok = MagicMock()
    tok.status_code = 200
    tok.content = b'{"access_token":"new-access","refresh_token":"new-refresh"}'
    tok.json.return_value = {"access_token": "new-access", "refresh_token": "new-refresh"}

    with patch("httpx.get", side_effect=[pr, meta]) as mock_get:
        with patch("httpx.post", return_value=tok) as mock_post:
            out = refresh_notion_access_token(
                "old-refresh",
                client_id="client-abc",
                redirect_uri="https://gw.test/api/v1/oauth/callback",
            )

    assert out == {"access_token": "new-access", "refresh_token": "new-refresh"}
    assert mock_get.call_count == 2
    kwargs = mock_post.call_args.kwargs
    assert kwargs["data"]["grant_type"] == "refresh_token"
    assert kwargs["data"]["refresh_token"] == "old-refresh"
    assert kwargs["data"]["client_id"] == "client-abc"
    assert kwargs["data"]["redirect_uri"] == "https://gw.test/api/v1/oauth/callback"


def test_refresh_notion_access_token_keeps_refresh_when_not_rotated() -> None:
    pr = MagicMock()
    pr.raise_for_status = MagicMock()
    pr.json.return_value = {"authorization_servers": ["https://auth.notion.test"]}
    meta = MagicMock()
    meta.raise_for_status = MagicMock()
    meta.json.return_value = {"token_endpoint": "https://auth.notion.test/token"}
    tok = MagicMock()
    tok.status_code = 200
    tok.content = b'{"access_token":"only-access"}'
    tok.json.return_value = {"access_token": "only-access"}

    with patch("httpx.get", side_effect=[pr, meta]):
        with patch("httpx.post", return_value=tok):
            out = refresh_notion_access_token("keep-me", client_id="cid")

    assert out == {"access_token": "only-access", "refresh_token": "keep-me"}


def test_resolve_notion_bearer_refreshes_stale_token_and_persists() -> None:
    db = MagicMock()
    db._read_only = True
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)

    def _resolve_setting(**kwargs):
        key = kwargs.get("key")
        if key == "mcp_notion.bearer":
            return {"value": "stale-access"}
        if key == "mcp_notion.refresh":
            return {"value": "live-refresh"}
        if key == "notion.client_id":
            return {"value": "notion-client"}
        return {"value": ""}

    with patch(
        "duckclaw.admin_mcp_connectors.resolve_runtime_setting",
        side_effect=lambda *a, **k: _resolve_setting(**k),
    ):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            return_value={"value_text": "stale-access", "updated_at": stale_ts},
        ):
            with patch(
                "duckclaw.mcp_notion_oauth.refresh_notion_access_token",
                return_value={"access_token": "fresh-access", "refresh_token": "fresh-refresh"},
            ) as mock_refresh:
                with patch(
                    "duckclaw.mcp_connector_oauth.persist_mcp_connector_oauth_tokens"
                ) as mock_persist:
                    assert resolve_connector_bearer_token(db, _notion_connector()) == "fresh-access"

    mock_refresh.assert_called_once()
    assert mock_refresh.call_args.kwargs["client_id"] == "notion-client"
    mock_persist.assert_called_once()
    assert mock_persist.call_args.kwargs["bearer_token"] == "fresh-access"
    assert mock_persist.call_args.kwargs["refresh_token"] == "fresh-refresh"


def test_resolve_notion_bearer_drops_dead_token_when_refresh_fails() -> None:
    db = MagicMock()
    db._read_only = True
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)

    def _resolve_setting(**kwargs):
        key = kwargs.get("key")
        if key == "mcp_notion.bearer":
            return {"value": "dead-access"}
        if key == "mcp_notion.refresh":
            return {"value": "dead-refresh"}
        if key == "notion.client_id":
            return {"value": "notion-client"}
        return {"value": ""}

    with patch(
        "duckclaw.admin_mcp_connectors.resolve_runtime_setting",
        side_effect=lambda *a, **k: _resolve_setting(**k),
    ):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            return_value={"value_text": "dead-access", "updated_at": stale_ts},
        ):
            with patch(
                "duckclaw.mcp_notion_oauth.refresh_notion_access_token",
                side_effect=ValueError("notion refresh failed: 401"),
            ):
                assert resolve_connector_bearer_token(db, _notion_connector()) == ""


def test_resolve_notion_bearer_returns_empty_without_refresh() -> None:
    db = MagicMock()
    db._read_only = True
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)

    def _resolve_setting(**kwargs):
        key = kwargs.get("key")
        if key == "mcp_notion.bearer":
            return {"value": "stale-access"}
        return {"value": ""}

    with patch(
        "duckclaw.admin_mcp_connectors.resolve_runtime_setting",
        side_effect=lambda *a, **k: _resolve_setting(**k),
    ):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            side_effect=[
                {"value_text": "stale-access", "updated_at": stale_ts},
                None,  # no refresh row
            ],
        ):
            assert resolve_connector_bearer_token(db, _notion_connector()) == ""
