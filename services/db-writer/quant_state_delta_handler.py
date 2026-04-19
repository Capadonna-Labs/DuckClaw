"""Ingesta QUANT_TRADER_STATE_DELTA: DDL + transiciones idempotentes de ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid as uuid_lib
from pathlib import Path
from typing import Any

import duckdb

from core.config import settings
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import db_root, validate_user_db_path
from models.quant_state_delta import QuantStateDelta, TradeSignalMutation, TradingMandateMutation

logger = logging.getLogger("db-writer.quant_state_delta")


# region agent log
def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    try:
        pl = {
            "sessionId": "c964f7",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "runId": "post-fix",
        }
        _p = Path("/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log")
        with _p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(pl, ensure_ascii=False) + "\n")
    except Exception:
        pass


# endregion


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

# Tablas creadas antes de session_uid / columnas usadas en INSERT: IF NOT EXISTS no altera esquema.
_QUANT_CORE_TRADE_SIGNALS_MIGRATION = """
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS session_uid VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS rationale VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS strategy_name VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS action VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS confidence_score DOUBLE;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS status VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
"""


def _coerce_mandate_id_to_uuid(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return str(uuid_lib.uuid4())
    try:
        uuid_lib.UUID(s)
        return s
    except ValueError:
        return str(uuid_lib.uuid5(uuid_lib.NAMESPACE_URL, "duckclaw:mandate:" + s))


def _infer_private_folder_uid(db_path: str) -> str | None:
    """Si la ruta es db/private/<carpeta>/..., devuelve el segmento de carpeta (coincide con user_vault_dir)."""
    try:
        path = Path(db_path).expanduser().resolve()
        rel = path.relative_to(db_root().resolve())
        parts = rel.parts
        if len(parts) >= 2 and parts[0] == "private":
            return str(parts[1])
    except (ValueError, OSError):
        pass
    return None


def _resolve_quant_user_id_for_path(user_id: str, target_db_path: str, tenant_id: str) -> str | None:
    """Alinea user_id del delta con db/private/<uid>/ cuando el productor envía default u otro slug."""
    if validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
        return str(user_id or "default").strip() or "default"
    inferred = _infer_private_folder_uid(target_db_path)
    if inferred and validate_user_db_path(inferred, target_db_path, tenant_id=tenant_id):
        return inferred
    return None


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
        mid = _coerce_mandate_id_to_uuid(str(mut.mandate_id))
        # region agent log
        if str(mut.mandate_id).strip() != mid:
            _agent_dbg(
                "H2",
                "quant_state_delta_handler._apply_delta",
                "mandate_id_coerced",
                {"raw": str(mut.mandate_id)[:120], "coerced": mid},
            )
        # endregion
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
                mid,
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
        mid = _coerce_mandate_id_to_uuid(str(mut.mandate_id))
        # region agent log
        if str(mut.mandate_id).strip() != mid:
            _agent_dbg(
                "H2",
                "quant_state_delta_handler._apply_delta",
                "trade_signal_mandate_coerced",
                {"raw": str(mut.mandate_id)[:120], "coerced": mid},
            )
        # endregion
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
                mid,
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
              (?, ?, 'cfd_auto', ?, 0.0, ?, ?, ?, now())
            ON CONFLICT (signal_id) DO UPDATE SET
              ticker=excluded.ticker,
              action=excluded.action,
              session_uid=excluded.session_uid,
              rationale=excluded.rationale,
              status=excluded.status,
              updated_at=now()
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
            SET status='EXECUTED', updated_at=now()
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
            SET status='DISCARDED', updated_at=now()
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
            SET status='FAILED', updated_at=now()
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
    raw_user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()
    resolved_uid = _resolve_quant_user_id_for_path(raw_user_id, target_db_path, tenant_id)
    if resolved_uid is None:
        logger.warning("QUANT_STATE_DELTA rejected: invalid db_path for user")
        # region agent log
        _agent_dbg(
            "H1",
            "quant_state_delta_handler._sync_handle_quant_state_delta",
            "path_rejected",
            {"raw_user_id": raw_user_id, "target_db_path": target_db_path[:240]},
        )
        # endregion
        return
    user_id = resolved_uid
    # region agent log
    if raw_user_id != user_id:
        _agent_dbg(
            "H1",
            "quant_state_delta_handler._sync_handle_quant_state_delta",
            "user_id_inferred_from_path",
            {"raw_user_id": raw_user_id, "resolved_user_id": user_id},
        )
    # endregion
    if not _validate_shared_acl(target_db_path, user_id=user_id, tenant_id=tenant_id):
        logger.warning("QUANT_STATE_DELTA rejected: no shared grant")
        return

    con = _connect_duckdb_writable(target_db_path)
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(_LEDGER_DDL)
        for _stmt in _QUANT_CORE_TRADE_SIGNALS_MIGRATION.strip().split(";"):
            _s = _stmt.strip()
            if _s:
                con.execute(_s)
        # region agent log
        _agent_dbg(
            "H3",
            "quant_state_delta_handler._sync_handle_quant_state_delta",
            "quant_core_trade_signals_migration_applied",
            {"delta_type": str(delta.delta_type or ""), "target_db_path": target_db_path[:240]},
        )
        # endregion
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
