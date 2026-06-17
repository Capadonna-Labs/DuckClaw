"""Read helpers for transversal HITL tables on DuckClaw vault handles."""

from __future__ import annotations

import json
import re
from typing import Any


def _rows_to_dicts(raw: Any, db: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(row) for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict):
            items = parsed.get("rows") or parsed.get("data") or []
            return [dict(row) for row in items if isinstance(row, dict)]
        return []

    if isinstance(raw, list):
        if not raw:
            return []
        if isinstance(raw[0], dict):
            return [dict(row) for row in raw]
        con = getattr(db, "_con", None)
        if con is not None and getattr(con, "description", None):
            names = [d[0] for d in con.description]
            return [dict(zip(names, row)) for row in raw]
        return [{"_raw": row} for row in raw]

    return []


def _query_rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        if hasattr(db, "query"):
            raw = db.query(sql, params) if params else db.query(sql)
            return _rows_to_dicts(raw, db)
        if params and hasattr(db, "execute"):
            result = db.execute(sql, list(params))
            if hasattr(result, "fetchdf"):
                raw = result.fetchdf().to_dict(orient="records")
                return _rows_to_dicts(raw, db)
            return _rows_to_dicts(result, db)
    except Exception:
        return []
    return []


def table_exists(db: Any, table_name: str) -> bool:
    name = (table_name or "").strip()
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return False
    rows = _query_rows(db, f"SELECT 1 AS ok FROM main.{name} LIMIT 1")
    return bool(rows)
