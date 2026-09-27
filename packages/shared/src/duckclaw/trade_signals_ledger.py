"""Resolve trade_signals across Capadonna ``finance_worker`` and ``quant_core``.

Agents/Capadonna write the ledger under ``finance_worker.trade_signals``.
DuckClaw execute/update paths historically only looked at ``quant_core``,
so a signal that exists in the vault ledger looked "missing" to execution
and the model filled the gap with EXIT vs BRACKET clarification theater.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

# Prefer Capadonna vault ledger, then legacy mirror schema.
TRADE_SIGNAL_SCHEMAS = ("finance_worker", "quant_core")

# Progressive projections — older/minimal tables may lack columns.
_SIGNAL_PROJECTIONS = (
    (
        "cast(signal_id AS VARCHAR) AS signal_id, action, strategy_name, "
        "rationale, order_qty, signal_type, ticker"
    ),
    (
        "cast(signal_id AS VARCHAR) AS signal_id, action, strategy_name, "
        "rationale, order_qty, signal_type"
    ),
    "cast(signal_id AS VARCHAR) AS signal_id, strategy_name, rationale, signal_type",
    "cast(signal_id AS VARCHAR) AS signal_id, strategy_name, rationale",
    "cast(signal_id AS VARCHAR) AS signal_id, signal_type",
    "cast(signal_id AS VARCHAR) AS signal_id",
)


def _normalize_row(row: Any, *, schema: str) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        out = {str(k): v for k, v in row.items()}
        out["schema"] = schema
        return out
    # Cursor description may be unavailable; map by known projection widths.
    keys_by_len = {
        7: ("signal_id", "action", "strategy_name", "rationale", "order_qty", "signal_type", "ticker"),
        6: ("signal_id", "action", "strategy_name", "rationale", "order_qty", "signal_type"),
        4: ("signal_id", "strategy_name", "rationale", "signal_type"),
        3: ("signal_id", "strategy_name", "rationale"),
        2: ("signal_id", "signal_type"),
        1: ("signal_id",),
    }
    keys = keys_by_len.get(len(row))
    if not keys:
        return {"signal_id": row[0] if row else None, "schema": schema}
    out = {k: row[i] for i, k in enumerate(keys)}
    out["schema"] = schema
    return out


def fetch_trade_signal_row(
    con: Any,
    signal_id: str,
    *,
    schemas: tuple[str, ...] = TRADE_SIGNAL_SCHEMAS,
) -> dict[str, Any] | None:
    """Return one trade_signals row from the first schema that has it."""
    sid = (signal_id or "").strip()
    if not sid or con is None:
        return None
    for schema in schemas:
        for projection in _SIGNAL_PROJECTIONS:
            sql = (
                f"SELECT {projection} FROM {schema}.trade_signals "
                "WHERE lower(cast(signal_id AS VARCHAR)) = lower(?) LIMIT 1"
            )
            try:
                cur = con.execute(sql, [sid])
                if hasattr(cur, "fetchone"):
                    row = cur.fetchone()
                else:
                    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                    row = rows[0] if rows else None
            except Exception:
                _log.debug(
                    "trade_signals fetch failed schema=%s projection=%s",
                    schema,
                    projection[:40],
                    exc_info=True,
                )
                continue
            if row:
                return _normalize_row(row, schema=schema)
    return None


def fetch_trade_signal_row_from_path(
    vault_db_path: str,
    signal_id: str,
    *,
    schemas: tuple[str, ...] = TRADE_SIGNAL_SCHEMAS,
) -> dict[str, Any] | None:
    """Open DuckDB read-only and resolve a trade signal by id."""
    path = (vault_db_path or "").strip()
    sid = (signal_id or "").strip()
    if not path or not sid:
        return None
    try:
        import duckdb

        con = duckdb.connect(path, read_only=True)
        try:
            return fetch_trade_signal_row(con, sid, schemas=schemas)
        finally:
            con.close()
    except Exception:
        _log.debug("trade_signals path fetch failed path=%s", path, exc_info=True)
        return None


def mark_trade_signal_executed(
    conn: Any,
    signal_id: str,
    executed_at: str,
    *,
    schemas: tuple[str, ...] = TRADE_SIGNAL_SCHEMAS,
) -> list[str]:
    """UPDATE executed_at on every schema that has the signal. Returns schemas touched."""
    sid = (signal_id or "").strip()
    if not sid or conn is None:
        return []
    touched: list[str] = []
    for schema in schemas:
        try:
            conn.execute(
                f"""
                UPDATE {schema}.trade_signals
                SET executed_at = ?
                WHERE lower(cast(signal_id AS VARCHAR)) = lower(?)
                """,
                [executed_at, sid],
            )
            probe = conn.execute(
                f"""
                SELECT 1 FROM {schema}.trade_signals
                WHERE lower(cast(signal_id AS VARCHAR)) = lower(?)
                LIMIT 1
                """,
                [sid],
            ).fetchone()
            if probe:
                touched.append(schema)
        except Exception:
            _log.debug(
                "trade_signals executed_at update skipped schema=%s",
                schema,
                exc_info=True,
            )
    return touched
