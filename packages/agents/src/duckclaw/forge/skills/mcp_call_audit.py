"""Audit row per external (MCP) tool call: who called what, how long, ok or error, and the payload sizes.

The arguments and the result are never stored (they can carry keys or personal data). The row is a typed command
for the DB-Writer, enqueued fire-and-forget: an audit failure must never fail or slow the tool call.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def record_mcp_call(
    db: Any,
    connector: dict[str, Any],
    tool_name: str,
    *,
    status: str,
    started: float,
    args_bytes: int,
    result_bytes: int = 0,
    error: str = "",
) -> None:
    """Enqueue one ``append_tool_call_log`` row; ``started`` is a ``time.monotonic()`` reading. Never raises."""
    try:
        raw_path = str(getattr(db, "_path", "") or "").strip()
        if not raw_path or raw_path == ":memory:":
            return
        from duckclaw.db_write_fire_and_forget import enqueue_write_command
        from duckclaw.forge.skills.knowledge_tool_context import (
            get_knowledge_tool_tenant_id,
            get_knowledge_tool_worker_uid,
            get_session_chat_id,
        )
        from duckclaw.media_usage_log import _infer_user_id_for_queue
        from duckclaw.write_commands import AppendToolCallLogCommand

        resolved = str(Path(raw_path).expanduser().resolve())
        command = AppendToolCallLogCommand(
            tenant_id=str(get_knowledge_tool_tenant_id() or "default"),
            id=f"TOOL-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            session_id=str(get_session_chat_id() or ""),
            worker_id=str(get_knowledge_tool_worker_uid() or ""),
            connector_id=str(connector.get("connector_id") or ""),
            tool_name=str(tool_name or ""),
            status="error" if status == "error" else "ok",
            duration_ms=int((time.monotonic() - started) * 1000),
            args_bytes=int(args_bytes),
            result_bytes=int(result_bytes),
            error=str(error or "")[:160],
        )
        enqueue_write_command(command, db_path=resolved, user_id=_infer_user_id_for_queue(resolved))
    except Exception:  # noqa: BLE001
        _log.debug("mcp_call_audit: row not recorded", exc_info=True)
