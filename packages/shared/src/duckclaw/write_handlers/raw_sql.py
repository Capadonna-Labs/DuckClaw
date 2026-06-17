"""Legacy raw SQL typed write handler."""

from __future__ import annotations

from typing import Any

from duckclaw.write_handlers.registry import register_handler


def _apply_raw_sql(conn: Any, payload: dict) -> None:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("query required")
    raw_params = payload.get("params") or []
    params = list(raw_params) if isinstance(raw_params, list) else list(raw_params)
    conn.execute(query, params)


register_handler("raw_sql", _apply_raw_sql)
