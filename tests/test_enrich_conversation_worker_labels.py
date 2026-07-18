"""Enrich conversation list with catalog display names."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.admin_conversations import (
    AdminConversationMeta,
    enrich_conversations_worker_display_names,
)


def test_enrich_conversations_worker_display_names() -> None:
    items = [
        AdminConversationMeta(
            session_id="s1",
            tenant_id="t1",
            last_worker_id="d",
            message_count=2,
        ),
        AdminConversationMeta(
            session_id="s2",
            tenant_id="t1",
            last_worker_id="missing",
            message_count=1,
        ),
    ]

    fake_db = MagicMock()

    def _lookup(_db, *, tenant_id, worker_id):
        if worker_id == "d":
            return {"worker_id": "d", "display_name": "DevOps Agent"}
        return None

    with (
        patch("core.admin_identity.open_gateway_db") as open_db,
        patch(
            "duckclaw.admin_worker_catalog.get_worker_by_tenant_worker_id",
            side_effect=_lookup,
        ),
    ):
        open_db.return_value.__enter__.return_value = fake_db
        open_db.return_value.__exit__.return_value = None
        enriched = enrich_conversations_worker_display_names(items, tenant_id="t1")

    assert enriched[0].last_worker_display_name == "DevOps Agent"
    assert enriched[1].last_worker_display_name == ""
