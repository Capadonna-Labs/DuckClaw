"""Read-only access to legacy ``agent_config`` rows in vault DuckDB files.

Read paths must not run DDL. Table creation belongs to ``bootstrap_core`` and
typed write handlers (``write_handlers.runtime._ensure_agent_config_table``).

Spec: docs/specs/features/platform/DB_FIRST_CORE_REFACTOR.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_AGENT_CONFIG_MISSING_WARNING = (
    "La tabla agent_config no existe en esta bóveda. "
    "Ejecuta: uv run python scripts/bootstrap_dbs.py"
)


@dataclass(frozen=True)
class AgentConfigListResult:
    rows: list[dict[str, str]]
    warning: str | None = None


def _duckdb_table_exists(db: Any, table_name: str) -> bool:
    sql = (
        "SELECT count(*) AS n FROM information_schema.tables "
        f"WHERE table_name = '{table_name}'"
    )
    try:
        if hasattr(db, "query"):
            raw = db.query(sql)
            if isinstance(raw, str) and raw.strip().startswith("["):
                parsed = json.loads(raw)
                if parsed and isinstance(parsed[0], dict):
                    return int(parsed[0].get("n") or 0) > 0
            return False
        result = db.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        )
        if hasattr(result, "fetchone"):
            row = result.fetchone()
        elif isinstance(result, list) and result:
            row = result[0]
        else:
            row = None
        return bool(row and int(row[0] or 0) > 0)
    except Exception:
        return False


def _fetch_agent_config_rows(db: Any) -> list[dict[str, str]]:
    if hasattr(db, "query"):
        raw = db.query("SELECT key, value FROM agent_config ORDER BY key")
        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
        if not isinstance(parsed, list):
            return []
        return [
            {"key": str(row.get("key") or ""), "value": str(row.get("value") or "")}
            for row in parsed
            if isinstance(row, dict)
        ]
    result = db.execute("SELECT key, value FROM agent_config ORDER BY key")
    rows = result.fetchall() if hasattr(result, "fetchall") else result
    return [{"key": str(key or ""), "value": str(value or "")} for key, value in (rows or [])]


def list_agent_config_entries(db: Any) -> AgentConfigListResult:
    """Return all agent_config key/value pairs without mutating the vault schema."""
    if not _duckdb_table_exists(db, "agent_config"):
        return AgentConfigListResult(rows=[], warning=_AGENT_CONFIG_MISSING_WARNING)
    try:
        return AgentConfigListResult(rows=_fetch_agent_config_rows(db))
    except Exception as exc:
        msg = str(exc)
        if "agent_config" in msg.lower() and "does not exist" in msg.lower():
            return AgentConfigListResult(rows=[], warning=_AGENT_CONFIG_MISSING_WARNING)
        raise
