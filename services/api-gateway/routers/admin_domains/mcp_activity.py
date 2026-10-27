"""Activity of external (MCP) tool calls, read from ``tool_call_log`` (rows are written by the DB-Writer; see mcp_call_audit)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query

from core.admin_identity import open_gateway_db
from routers.admin_domains.admin_common import actor_from_header, require_admin_key
from routers.admin_domains.mcp_connectors import _actor_profile

router = APIRouter(prefix="/mcp/activity", tags=["admin-mcp-activity"])


def _rows(db: Any, sql: str) -> list[dict[str, Any]]:
    raw = db.query(sql)
    data = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [r for r in data if isinstance(r, dict)]


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''")[:128] + "'"


def read_activity(db: Any, tenant_id: str, *, days: int, limit: int, connector_id: str = "") -> dict[str, Any]:
    """Per-tool summary and the latest calls of one tenant; an empty answer (``table_ready`` false) until the first call is recorded."""
    where = f"tenant_id = {_quote(tenant_id)} AND created_at >= CURRENT_TIMESTAMP - INTERVAL {int(days)} DAY"
    if connector_id:
        where += f" AND connector_id = {_quote(connector_id)}"
    try:
        summary = _rows(
            db,
            "SELECT connector_id, tool_name, count(*) AS calls, sum(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors, "
            f"CAST(round(avg(duration_ms)) AS INTEGER) AS avg_ms, CAST(max(created_at) AS VARCHAR) AS last_at FROM tool_call_log WHERE {where} "
            "GROUP BY connector_id, tool_name ORDER BY calls DESC LIMIT 200",
        )
        recent = _rows(
            db,
            "SELECT CAST(created_at AS VARCHAR) AS created_at, connector_id, tool_name, worker_id, status, duration_ms, args_bytes, result_bytes, error "
            f"FROM tool_call_log WHERE {where} ORDER BY created_at DESC LIMIT {int(limit)}",
        )
    except Exception:  # noqa: BLE001  the table does not exist until the first recorded call
        return {"table_ready": False, "summary": [], "recent": []}
    return {"table_ready": True, "summary": summary, "recent": recent}


@router.get("", dependencies=[Depends(require_admin_key)])
async def mcp_activity(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    connector_id: str = Query(""),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    tenant_id = str(_actor_profile(actor).get("tenant_id") or "default")

    def _read() -> dict[str, Any]:
        with open_gateway_db(read_only=True) as db:
            return read_activity(db, tenant_id, days=days, limit=limit, connector_id=connector_id.strip())

    return await asyncio.to_thread(_read)
