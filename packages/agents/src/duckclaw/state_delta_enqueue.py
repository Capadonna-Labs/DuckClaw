"""Transversal state-delta enqueue helpers (no product-extension imports)."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def push_extension_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    """Route known transversal delta types; unknown product deltas are ignored in core."""
    delta_type = str(payload.get("delta_type") or "").strip().upper()
    if delta_type in {"CONTEXT_INJECTION", "SEMANTIC_MEMORY_UPSERT"}:
        from duckclaw.forge.skills.context_injection_delta import push_context_injection_sync

        mutation = dict(payload.get("mutation") or {})
        if delta_type == "SEMANTIC_MEMORY_UPSERT":
            topic = str(mutation.get("topic") or "").strip()
            insight = str(mutation.get("insight") or "").strip()
            raw_text = f"{topic}: {insight}".strip(": ").strip() if topic or insight else ""
            if not raw_text:
                return False
            mutation = {"raw_text": raw_text, "source": str(mutation.get("source") or "dreamer_job")}
        routed = {
            "tenant_id": str(payload.get("tenant_id") or "default"),
            "delta_type": "CONTEXT_INJECTION",
            "user_id": str(payload.get("user_id") or "default"),
            "target_db_path": str(payload.get("target_db_path") or ""),
            "mutation": mutation,
        }
        return push_context_injection_sync(routed, duckclaw_db=duckclaw_db)

    if delta_type == "CONVERSATION_COMPACTION":
        _log.warning(
            "CONVERSATION_COMPACTION omitido en core transversal; usa mantenimiento admin/DB-writer"
        )
        return False

    _log.warning("state delta desconocido en core: %s", delta_type or "<empty>")
    return False
