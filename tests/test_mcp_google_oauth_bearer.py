"""Google OAuth bearer resolution when refresh is revoked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token


def test_resolve_bearer_drops_stale_token_when_refresh_revoked() -> None:
    db = MagicMock()
    db._read_only = True
    connector = {
        "auth_kind": "bearer",
        "auth_secret_key": "mcp_google_gmail.bearer",
        "tenant_id": "tenant-a",
        "owner_email": "user@example.com",
        "connector_id": "mcp_google_gmail",
        "preset_id": "google_gmail",
    }

    with patch(
        "duckclaw.admin_mcp_connectors.resolve_runtime_setting",
        side_effect=[
            {"value": "dead-access-token"},
            {"value": "dead-refresh-token"},
        ],
    ):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            return_value=None,
        ):
            with patch("httpx.get") as mock_get:
                mock_get.return_value.status_code = 400
                with patch(
                    "duckclaw.mcp_google_workspace_oauth.refresh_google_access_token",
                    return_value="",
                ):
                    assert resolve_connector_bearer_token(db, connector) == ""
