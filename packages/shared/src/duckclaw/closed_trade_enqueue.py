"""Enqueue verified closed trades onto the singleton DuckDB write queue.

Capadonna ``trading_session_fly._enqueue_closed_trade`` should call
``enqueue_closed_trade_recorded`` after ``match_closing_fills`` succeeds so
``quant_core.closed_trades`` is written only by DuckClaw-DB-Writer.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def closed_trade_command_from_mutation(mutation: dict[str, Any], *, tenant_id: str = "default"):
    """Build ``InsertClosedTradeCommand`` from a Capadonna ``draft_to_mutation`` dict."""
    from duckclaw.write_commands import InsertClosedTradeCommand

    return InsertClosedTradeCommand(
        tenant_id=str(tenant_id or "default").strip() or "default",
        ticker=str(mutation.get("ticker") or "").strip().upper(),
        fill_id=str(mutation.get("fill_id") or "").strip(),
        closed_at=str(mutation.get("closed_at") or "").strip(),
        qty=float(mutation["qty"]),
        entry_px=float(mutation["entry_px"]),
        exit_px=float(mutation["exit_px"]),
        pnl=float(mutation["pnl"]),
        ret_pct=float(mutation["ret_pct"]),
        side=str(mutation.get("side") or "").strip().upper(),  # type: ignore[arg-type]
        session_uid=str(mutation.get("session_uid") or "").strip(),
        signal_id=str(mutation.get("signal_id") or "").strip(),
    )


def enqueue_closed_trade_recorded(
    mutation: dict[str, Any],
    *,
    db_path: str,
    user_id: str = "default",
    tenant_id: str = "default",
    duckclaw_db: Any | None = None,
) -> str | None:
    """Enqueue ``insert_closed_trade`` for the vault at ``db_path``.

    Optionally releases ``duckclaw_db``'s file handle when it points at the same
    vault so DB-Writer can open RW (same pattern as Capadonna state-delta push).

    Returns task_id on success, None if mutation is incomplete.
    """
    fill_id = str((mutation or {}).get("fill_id") or "").strip()
    ticker = str((mutation or {}).get("ticker") or "").strip()
    if not fill_id or not ticker:
        return None

    path = str(db_path or "").strip()
    if not path or path == ":memory:":
        _log.warning("enqueue_closed_trade_recorded: db_path vacío")
        return None

    if duckclaw_db is not None:
        try:
            from duckclaw.state_delta_vault import release_ro_vault_for_remote_writer

            release_ro_vault_for_remote_writer(
                {"target_db_path": path},
                duckclaw_db,
            )
        except Exception:
            release = getattr(duckclaw_db, "release_file_handle_for_external_writer", None)
            if callable(release):
                try:
                    release()
                except Exception:
                    pass

    from duckclaw.db_write_queue import enqueue_typed_command

    cmd = closed_trade_command_from_mutation(mutation, tenant_id=tenant_id)
    return enqueue_typed_command(
        cmd,
        db_path=path,
        user_id=str(user_id or "default"),
    )
