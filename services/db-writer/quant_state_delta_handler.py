"""Ingesta QUANT_TRADER_STATE_DELTA: DDL + transiciones idempotentes de ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb

from core.config import settings
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import db_root, validate_user_db_path
from models.quant_state_delta import (
    ConversationCompactionMutation,
    IntradayMocAccumMutation,
    QuantStateDelta,
    SemanticMemoryUpsertMutation,
    TradeSignalMutation,
    TradingMandateMutation,
)

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

CREATE TABLE IF NOT EXISTS quant_core.hrp_mandates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker VARCHAR(20) NOT NULL,
  hrp_weight DOUBLE NOT NULL,
  hrp_weight_capped DOUBLE NOT NULL,
  lookback_days INTEGER NOT NULL,
  n_observations INTEGER NOT NULL,
  computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  valid_until TIMESTAMP NOT NULL,
  shrinkage_method VARCHAR(50) DEFAULT 'ledoit_wolf'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hrp_mandates_ticker_day
  ON quant_core.hrp_mandates (ticker, date_trunc('day', computed_at));

CREATE TABLE IF NOT EXISTS quant_core.session_ticks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_uid VARCHAR NOT NULL,
  tick_number INTEGER NOT NULL,
  fired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  tickers_processed VARCHAR[],
  signals_proposed INTEGER DEFAULT 0,
  cfd_summary JSON,
  outcome VARCHAR
);
ALTER TABLE quant_core.session_ticks ADD COLUMN IF NOT EXISTS moc_executed BOOLEAN DEFAULT FALSE;
ALTER TABLE quant_core.session_ticks ADD COLUMN IF NOT EXISTS moc_notional DECIMAL(15,2);
ALTER TABLE quant_core.session_ticks ADD COLUMN IF NOT EXISTS moc_n_orders INTEGER;
"""

_INTRADAY_MOC_ACCUM_DDL = """
CREATE TABLE IF NOT EXISTS quant_core.intraday_moc_accum (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_uid VARCHAR NOT NULL,
  ticker VARCHAR NOT NULL,
  trading_date DATE NOT NULL,
  payload JSON NOT NULL DEFAULT '{}',
  finalized_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(session_uid, ticker, trading_date)
);
"""

# Tablas creadas antes de session_uid / columnas usadas en INSERT: IF NOT EXISTS no altera esquema.
_DREAMER_SEMANTIC_TELEGRAM_DDL = """
CREATE SCHEMA IF NOT EXISTS main;
CREATE TABLE IF NOT EXISTS main.semantic_memory (
  id VARCHAR PRIMARY KEY,
  content TEXT NOT NULL,
  source VARCHAR DEFAULT 'manual_injection',
  embedding FLOAT[384],
  embedding_status VARCHAR DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS topic VARCHAR;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS confidence_score DOUBLE;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
CREATE TABLE IF NOT EXISTS telegram_conversation (
  chat_id BIGINT,
  role TEXT,
  content TEXT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_QUANT_CORE_TRADE_SIGNALS_MIGRATION = """
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS session_uid VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS rationale VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS strategy_name VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS action VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS confidence_score DOUBLE;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS status VARCHAR;
ALTER TABLE quant_core.trade_signals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
"""


def _merge_intraday_accum_payload(existing: Any, patch: dict[str, object]) -> str:
    base: dict[str, object] = {}
    if existing is not None:
        try:
            if isinstance(existing, str) and existing.strip():
                parsed = json.loads(existing)
                if isinstance(parsed, dict):
                    base = dict(parsed)
            elif isinstance(existing, dict):
                base = dict(existing)
        except (json.JSONDecodeError, TypeError):
            base = {}
    merged = {**base, **patch}
    return json.dumps(merged, ensure_ascii=False)


def _resolve_trading_date_for_accum(raw: str) -> str:
    from datetime import datetime

    s = (raw or "").strip()
    if s and len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Bogota")).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


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

    if dt == "INTRADAY_MOC_ACCUM_UPSERT":
        mut = IntradayMocAccumMutation.model_validate(delta.mutation)
        td = _resolve_trading_date_for_accum(mut.trading_date)
        tku = str(mut.ticker or "").strip().upper()
        if not tku:
            raise ValueError("ticker requerido para INTRADAY_MOC_ACCUM_UPSERT")
        su = str(mut.session_uid or "").strip()
        if not su:
            raise ValueError("session_uid requerido para INTRADAY_MOC_ACCUM_UPSERT")
        row = con.execute(
            """
            SELECT id, payload, finalized_at
            FROM quant_core.intraday_moc_accum
            WHERE session_uid = ? AND ticker = ? AND trading_date = ?::DATE
            """,
            (su, tku, td),
        ).fetchone()
        if row is not None and row[2] is not None:
            raise ValueError("intraday_moc_accum ya finalizado para session/ticker/fecha")
        patch = mut.patch if isinstance(mut.patch, dict) else {}
        prev_payload: Any = row[1] if row is not None else None
        merged_json = _merge_intraday_accum_payload(prev_payload, patch)
        if row is None:
            con.execute(
                """
                INSERT INTO quant_core.intraday_moc_accum
                  (id, session_uid, ticker, trading_date, payload, updated_at)
                VALUES (gen_random_uuid(), ?, ?, ?::DATE, ?::JSON, now())
                """,
                (su, tku, td, merged_json),
            )
        else:
            con.execute(
                """
                UPDATE quant_core.intraday_moc_accum
                SET payload = ?::JSON, updated_at = now()
                WHERE id = ? AND finalized_at IS NULL
                """,
                (merged_json, row[0]),
            )
        return

    if dt == "TRADE_SIGNAL_PROPOSED":
        mut = TradeSignalMutation.model_validate(delta.mutation)
        mid = _coerce_mandate_id_to_uuid(str(mut.mandate_id))
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
        strat_s = (mut.strategy_name or "cfd_auto").strip() or "cfd_auto"
        con.execute(
            """
            INSERT INTO quant_core.trade_signals
              (signal_id, ticker, strategy_name, action, confidence_score, session_uid, rationale, status, updated_at)
            VALUES
              (?, ?, ?, ?, 0.0, ?, ?, ?, now())
            ON CONFLICT (signal_id) DO UPDATE SET
              ticker=excluded.ticker,
              strategy_name=excluded.strategy_name,
              action=excluded.action,
              session_uid=excluded.session_uid,
              rationale=excluded.rationale,
              status=excluded.status,
              updated_at=now()
            """,
            (
                mut.signal_id,
                mut.ticker.upper(),
                strat_s,
                "BUY" if mut.signal_type == "ENTRY" else "SELL",
                mut.session_uid,
                mut.rationale,
                st,
            ),
        )
        return

    if dt == "SEMANTIC_MEMORY_UPSERT":
        mut = SemanticMemoryUpsertMutation.model_validate(delta.mutation)
        tbl = (mut.table or "").strip().lower()
        if tbl != "main.semantic_memory":
            raise ValueError("SEMANTIC_MEMORY_UPSERT: mutation.table debe ser main.semantic_memory")
        row_id = (mut.memory_id or "").strip() or str(uuid_lib.uuid4())
        con.execute(
            """
            INSERT INTO main.semantic_memory
              (id, content, source, topic, confidence_score, updated_at, embedding_status)
            VALUES (?, ?, ?, ?, ?, now(), 'PENDING')
            ON CONFLICT (id) DO UPDATE SET
              content = excluded.content,
              source = excluded.source,
              topic = excluded.topic,
              confidence_score = excluded.confidence_score,
              updated_at = now()
            """,
            (
                row_id,
                mut.insight,
                mut.source,
                mut.topic,
                float(mut.confidence_score),
            ),
        )
        return

    if dt == "CONVERSATION_COMPACTION":
        mut = ConversationCompactionMutation.model_validate(delta.mutation)
        tbn = (mut.table or "").strip().lower()
        if tbn != "telegram_conversation":
            raise ValueError("CONVERSATION_COMPACTION: mutation.table debe ser telegram_conversation")
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(mut.days))
        con.execute(
            """
            DELETE FROM telegram_conversation
            WHERE chat_id = ? AND received_at < ?
            """,
            (mut.chat_id, cutoff),
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
        return
    user_id = resolved_uid
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
        for _stmt in _INTRADAY_MOC_ACCUM_DDL.strip().split(";"):
            _s = _stmt.strip()
            if _s:
                con.execute(_s)
        for _stmt in _DREAMER_SEMANTIC_TELEGRAM_DDL.strip().split(";"):
            _s = _stmt.strip()
            if _s:
                con.execute(_s)
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
