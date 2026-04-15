"""Ingesta QUANT_TRADER_STATE_DELTA: DDL + transiciones idempotentes de ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import duckdb

from core.config import settings
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import validate_user_db_path
from models.quant_state_delta import QuantStateDelta, TradeSignalMutation, TradingMandateMutation

logger = logging.getLogger("db-writer.quant_state_delta")

_LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS finance_worker;

CREATE SCHEMA IF NOT EXISTS quant_core;

CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
  id VARCHAR PRIMARY KEY,
  mode VARCHAR NOT NULL,
  tickers VARCHAR NOT NULL DEFAULT '',
  session_uid VARCHAR,
  session_goal JSON,
  status VARCHAR NOT NULL DEFAULT 'ACTIVE',
  anchor_equity DOUBLE,
  peak_equity DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.trading_risk_constraints (
  id VARCHAR PRIMARY KEY,
  max_drawdown_pct DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.trading_mandates (
  mandate_id UUID PRIMARY KEY,
  source_worker VARCHAR,
  asset_class VARCHAR,
  direction VARCHAR,
  max_weight_pct DECIMAL(5,2),
  status VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.trade_signals (
  signal_id UUID PRIMARY KEY,
  mandate_id UUID REFERENCES finance_worker.trading_mandates(mandate_id),
  ticker VARCHAR,
  signal_type VARCHAR,
  proposed_weight DECIMAL(5,2),
  sandbox_backtest_cid VARCHAR,
  human_approved BOOLEAN DEFAULT FALSE,
  status VARCHAR,
  rationale VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.trade_signals (
  signal_id UUID PRIMARY KEY,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ticker VARCHAR,
  strategy_name VARCHAR,
  action VARCHAR,
  confidence_score DOUBLE,
  target_price DOUBLE,
  stop_loss DOUBLE,
  session_uid VARCHAR,
  rationale VARCHAR,
  status VARCHAR DEFAULT 'PENDING_HITL',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _connect_duckdb_writable(path: str, *, attempts: int = 12, base_sleep_s: float = 0.25) -> duckdb.DuckDBPyConnection:
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_duckdb_lock_error(exc):
                delay = base_sleep_s * min(i + 1, 8)
                logger.warning("QUANT_STATE_DELTA DuckDB lock intento %s/%s, reintento en %.2fs: %s", i + 1, attempts, delay, exc)
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


def _validate_shared_acl(target_db_path: str, *, user_id: str, tenant_id: str) -> bool:
    try:
        from duckclaw import DuckClaw
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        if not path_is_under_shared_tree(target_db_path):
            return True
        acl_path = get_gateway_db_path()
        acl_con = DuckClaw(acl_path, read_only=True)
        try:
            return bool(
                user_may_access_shared_path(
                    acl_con,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    shared_db_path=target_db_path,
                )
            )
        finally:
            _ac = getattr(acl_con, "_con", None)
            if _ac is not None:
                try:
                    _ac.close()
                except Exception:
                    pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("QUANT_STATE_DELTA ACL shared check skipped/failed: %s", exc)
        return True


def _apply_delta(con: duckdb.DuckDBPyConnection, delta: QuantStateDelta) -> None:
    dt = str(delta.delta_type or "").strip()
    if dt == "MANDATE_UPSERT":
        mut = TradingMandateMutation.model_validate(delta.mutation)
        con.execute(
            """
            INSERT INTO finance_worker.trading_mandates
              (mandate_id, source_worker, asset_class, direction, max_weight_pct, status)
            VALUES
              (?, ?, ?, ?, ?, ?)
            ON CONFLICT (mandate_id) DO UPDATE SET
              source_worker=excluded.source_worker,
              asset_class=excluded.asset_class,
              direction=excluded.direction,
              max_weight_pct=excluded.max_weight_pct,
              status=excluded.status
            """,
            (
                mut.mandate_id,
                mut.source_worker,
                mut.asset_class,
                mut.direction,
                float(mut.max_weight_pct),
                mut.status,
            ),
        )
        return

    if dt == "TRADE_SIGNAL_PROPOSED":
        mut = TradeSignalMutation.model_validate(delta.mutation)
        st = "PENDING_HITL" if mut.status == "AWAITING_HITL" else mut.status
        con.execute(
            """
            INSERT INTO finance_worker.trade_signals
              (signal_id, mandate_id, ticker, signal_type, proposed_weight, sandbox_backtest_cid,
               human_approved, status, rationale)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (signal_id) DO UPDATE SET
              mandate_id=excluded.mandate_id,
              ticker=excluded.ticker,
              signal_type=excluded.signal_type,
              proposed_weight=excluded.proposed_weight,
              sandbox_backtest_cid=excluded.sandbox_backtest_cid,
              status=excluded.status,
              rationale=excluded.rationale
            """,
            (
                mut.signal_id,
                mut.mandate_id,
                mut.ticker.upper(),
                mut.signal_type,
                float(mut.proposed_weight),
                mut.sandbox_backtest_cid,
                bool(mut.human_approved),
                st,
                mut.rationale,
            ),
        )
        con.execute(
            """
            INSERT INTO quant_core.trade_signals
              (signal_id, ticker, strategy_name, action, confidence_score, session_uid, rationale, status, updated_at)
            VALUES
              (?, ?, 'cfd_auto', ?, 0.0, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (signal_id) DO UPDATE SET
              ticker=excluded.ticker,
              action=excluded.action,
              session_uid=excluded.session_uid,
              rationale=excluded.rationale,
              status=excluded.status,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                mut.signal_id,
                mut.ticker.upper(),
                "BUY" if mut.signal_type == "ENTRY" else "SELL",
                mut.session_uid,
                mut.rationale,
                st,
            ),
        )
        return

    sid = str((delta.mutation or {}).get("signal_id") or "").strip()
    if not sid:
        raise ValueError("signal_id requerido para transición de señal")

    if dt == "TRADE_SIGNAL_APPROVED":
        con.execute(
            """
            UPDATE finance_worker.trade_signals
            SET human_approved=TRUE
            WHERE signal_id=?
            """,
            (sid,),
        )
        return

    if dt == "TRADE_SIGNAL_EXECUTED":
        con.execute(
            """
            UPDATE finance_worker.trade_signals
            SET human_approved=TRUE, status='EXECUTED'
            WHERE signal_id=?
            """,
            (sid,),
        )
        con.execute(
            """
            UPDATE quant_core.trade_signals
            SET status='EXECUTED', updated_at=CURRENT_TIMESTAMP
            WHERE signal_id=?
            """,
            (sid,),
        )
        return

    if dt == "TRADE_SIGNAL_DISCARDED":
        con.execute(
            """
            UPDATE finance_worker.trade_signals
            SET status='DISCARDED'
            WHERE signal_id=? AND status <> 'EXECUTED'
            """,
            (sid,),
        )
        con.execute(
            """
            UPDATE quant_core.trade_signals
            SET status='DISCARDED', updated_at=CURRENT_TIMESTAMP
            WHERE signal_id=? AND status <> 'EXECUTED'
            """,
            (sid,),
        )
        return

    if dt == "TRADE_SIGNAL_FAILED":
        con.execute(
            """
            UPDATE finance_worker.trade_signals
            SET status='FAILED'
            WHERE signal_id=? AND status NOT IN ('EXECUTED', 'DISCARDED')
            """,
            (sid,),
        )
        con.execute(
            """
            UPDATE quant_core.trade_signals
            SET status='FAILED', updated_at=CURRENT_TIMESTAMP
            WHERE signal_id=? AND status NOT IN ('EXECUTED', 'DISCARDED')
            """,
            (sid,),
        )
        return

    raise ValueError(f"delta_type no soportado: {dt}")


def _sync_handle_quant_state_delta(message: str) -> None:
    data = json.loads(message)
    delta = QuantStateDelta.model_validate(data)
    tenant_id = str(delta.tenant_id or "default").strip() or "default"
    user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()
    if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
        logger.warning("QUANT_STATE_DELTA rejected: invalid db_path for user")
        return
    if not _validate_shared_acl(target_db_path, user_id=user_id, tenant_id=tenant_id):
        logger.warning("QUANT_STATE_DELTA rejected: no shared grant")
        return

    con = _connect_duckdb_writable(target_db_path)
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(_LEDGER_DDL)
        _apply_delta(con, delta)
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


async def handle_quant_state_delta_message(redis_client: Any, message: str) -> None:
    qname = str(settings.QUANT_STATE_DELTA_QUEUE_NAME).strip()
    try:
        await asyncio.to_thread(_sync_handle_quant_state_delta, message)
    except Exception as exc:  # noqa: BLE001
        if _is_duckdb_lock_error(exc):
            logger.error("QUANT_STATE_DELTA DuckDB bloqueado tras reintentos; reencolando en %s: %s", qname, exc)
            if redis_client is not None:
                try:
                    await redis_client.rpush(qname, message)
                except Exception as rq_exc:  # noqa: BLE001
                    logger.error("QUANT_STATE_DELTA reencolado falló: %s", rq_exc)
            return
        logger.exception("QUANT_STATE_DELTA error procesando mensaje: %s", exc)
