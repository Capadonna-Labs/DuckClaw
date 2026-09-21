"""Google OAuth bearer resolution when refresh is revoked / actor mismatch."""

from __future__ import annotations

from datetime import datetime, timezone
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

    # Newest-secret SQL path returns dead access; refresh path returns dead refresh.
    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=("dead-access-token", datetime(2020, 1, 1, tzinfo=timezone.utc)))),
        MagicMock(fetchone=MagicMock(return_value=("dead-refresh-token", datetime(2020, 1, 1, tzinfo=timezone.utc)))),
    ]

    with patch(
        "duckclaw.mcp_google_workspace_oauth.refresh_google_access_token",
        return_value="",
    ):
        assert resolve_connector_bearer_token(db, connector) == ""


def test_resolve_bearer_prefers_newest_actor_over_stale_system_owner() -> None:
    """Fresh session OAuth must win even when connector.owner_email is still system."""
    db = MagicMock()
    db._read_only = True
    connector = {
        "auth_kind": "bearer",
        "auth_secret_key": "mcp_google_gmail.bearer",
        "tenant_id": "tenant-a",
        "owner_email": "system",
        "connector_id": "mcp_google_gmail",
        "preset_id": "google_gmail",
    }
    fresh_ts = datetime.now(timezone.utc)

    db.execute.side_effect = [
        # bearer newest
        MagicMock(fetchone=MagicMock(return_value=("fresh-user-access", fresh_ts))),
        # refresh newest (unused when age-fresh)
        MagicMock(fetchone=MagicMock(return_value=("fresh-user-refresh", fresh_ts))),
    ]

    with patch("httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        assert resolve_connector_bearer_token(db, connector) == "fresh-user-access"
        mock_get.assert_not_called()  # age-based freshness skipped tokeninfo
