"""Admin SSE alert for loop critical events."""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)


def notify_admin_alert(
    admin_chat_id: str,
    message: str,
    *,
    worker_id: str | None = None,
    tenant_id: str | None = None,
    distance_vector: dict[str, float] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> None:
    """Publish loop_critical alert via admin chat heartbeat SSE."""
    cid = (admin_chat_id or "").strip()
    if not cid:
        _log.debug("notify_admin_alert: no admin_chat_id; skip")
        return
    extra: dict[str, Any] = {"alert_type": "loop_critical"}
    if tenant_id:
        extra["tenant_id"] = tenant_id
    if distance_vector:
        extra["distance_vector"] = distance_vector
    if actions:
        extra["actions"] = actions
    text = (message or "").strip()
    if extra:
        text = f"{text}\n{json.dumps(extra, ensure_ascii=False)}"
    try:
        from duckclaw.graphs.chat_heartbeat import publish_admin_chat_heartbeat

        publish_admin_chat_heartbeat(
            cid,
            text,
            kind="loop_critical",
            worker_id=worker_id,
            artifact_tenant_id=tenant_id,
        )
    except Exception as exc:
        _log.warning("notify_admin_alert failed: %s", exc)
