# services/api-gateway/core/telegram_mcp_dlq.py
"""Cola de fallos (DLQ) Redis para egress Telegram vía MCP."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

_log = logging.getLogger("duckclaw.gateway.telegram_mcp_dlq")

TELEGRAM_MCP_DLQ_KEY = "duckclaw:telegram:dlq"


def redact_tool_args_for_dlq(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args)
    b64 = out.get("photo_base64")
    if isinstance(b64, str) and b64:
        h = hashlib.sha256(b64.encode("utf-8", errors="ignore")).hexdigest()[:16]
        out["photo_base64"] = f"<redacted len={len(b64)} sha16={h}>"
    tx = out.get("text")
    if isinstance(tx, str) and len(tx) > 400:
        out["text"] = tx[:400] + "…"
    return out


async def push_telegram_mcp_dlq(
    redis_client: Any,
    *,
    tenant_id: str,
    chat_id: str,
    tool: str,
    args: dict[str, Any],
    error: str,
) -> None:
    if redis_client is None:
        return
    payload = {
        "tenant_id": (tenant_id or "").strip() or "default",
        "chat_id": str(chat_id),
        "tool": tool,
        "args_redacted": redact_tool_args_for_dlq(tool, args),
        "error": (error or "")[:2000],
        "ts": int(time.time()),
    }
    try:
        await redis_client.lpush(TELEGRAM_MCP_DLQ_KEY, json.dumps(payload, ensure_ascii=False))
        _log.warning(
            "telegram MCP DLQ: encolado tool=%s chat_id=%s tenant=%s",
            tool,
            chat_id,
            tenant_id,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("telegram MCP DLQ: LPUSH falló: %s", exc)


def push_telegram_mcp_dlq_blocking(
    redis_url: str | None,
    *,
    tenant_id: str,
    chat_id: str,
    tool: str,
    args: dict[str, Any],
    error: str,
) -> None:
    if not redis_url:
        return
    try:
        import redis as sync_redis

        r = sync_redis.from_url(redis_url, decode_responses=True)
        payload = {
            "tenant_id": (tenant_id or "").strip() or "default",
            "chat_id": str(chat_id),
            "tool": tool,
            "args_redacted": redact_tool_args_for_dlq(tool, args),
            "error": (error or "")[:2000],
            "ts": int(time.time()),
        }
        r.lpush(TELEGRAM_MCP_DLQ_KEY, json.dumps(payload, ensure_ascii=False))
        r.close()
        _log.warning("telegram MCP DLQ (sync): tool=%s chat_id=%s", tool, chat_id)
    except Exception as exc:  # noqa: BLE001
        _log.warning("telegram MCP DLQ sync: falló: %s", exc)
