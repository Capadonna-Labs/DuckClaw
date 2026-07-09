"""Ingesta MEDITATE_STATE_DELTA: purge stale, quarantine memory, audit runs."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import duckdb

from core.config import settings
from db_writer_ops import push_dlq
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import validate_user_db_path
from models.loop_state_delta import LoopStateDelta

logger = logging.getLogger("db-writer.loop_state_delta")

_HARNESS_DDL = """
CREATE SCHEMA IF NOT EXISTS harness_core;

CREATE TABLE IF NOT EXISTS harness_core.loop_runs (
  run_id VARCHAR PRIMARY KEY,
  tenant_id VARCHAR NOT NULL,
  distance_vector JSON,
  actions_json JSON,
  status VARCHAR NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS harness_core.homeostasis_targets (
  tenant_id VARCHAR PRIMARY KEY,
  targets_json JSON,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _connect_duckdb_writable(
    path: str,
    *,
    attempts: int = 24,
    base_sleep_s: float = 0.35,
) -> duckdb.DuckDBPyConnection:
    """Open vault RW; gateway often holds RW for a whole agent turn."""
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_duckdb_lock_error(exc) and i < attempts - 1:
                delay = base_sleep_s * min(i + 1, 10)
                logger.warning(
                    "loop_state_delta DuckDB lock %s/%s, sleep %.2fs path=%s",
                    i + 1,
                    attempts,
                    delay,
                    path,
                )
                time.sleep(delay)
                continue
            raise
    if last is not None:
        raise last
    raise RuntimeError("connect duckdb failed")


def _ensure_harness_schema(con: duckdb.DuckDBPyConnection) -> None:
    for stmt in _HARNESS_DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)


def _apply_purge_stale(con: duckdb.DuckDBPyConnection, delta: LoopStateDelta) -> None:
    m = delta.purge_mutation()
    if not m.task_ids:
        return
    table = (m.source_table or "main.task_audit_log").strip()
    if "." not in table or not table.replace(".", "").replace("_", "").isalnum():
        raise ValueError(f"invalid source_table: {table}")
    cols = {
        str(row[1])
        for row in con.execute(f"PRAGMA table_info('{table}')").fetchall()
    }
    if "status" not in cols:
        raise ValueError(f"source_table without status column: {table}")
    id_col = "task_id" if "task_id" in cols else "id"
    updated_clause = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in cols else ""
    for tid in m.task_ids[:200]:
        esc = str(tid).replace("'", "''")
        con.execute(
            f"UPDATE {table} SET status = 'CANCELLED'{updated_clause} "
            f"WHERE CAST({id_col} AS VARCHAR) = '{esc}'"
        )


def _apply_quarantine(con: duckdb.DuckDBPyConnection, delta: LoopStateDelta) -> None:
    m = delta.quarantine_mutation()
    for mid in m.memory_ids[:200]:
        esc = str(mid).replace("'", "''")
        con.execute(
            "UPDATE main.semantic_memory SET embedding_status = 'QUARANTINE', "
            f"updated_at = CURRENT_TIMESTAMP WHERE id = '{esc}'"
        )


def _apply_manifest(con: duckdb.DuckDBPyConnection, delta: LoopStateDelta) -> None:
    m = delta.manifest_mutation()
    tid = str(delta.tenant_id or "default")
    con.execute(
        """
        INSERT INTO harness_core.homeostasis_targets (tenant_id, targets_json)
        VALUES (?, ?)
        ON CONFLICT (tenant_id) DO UPDATE SET
          targets_json = excluded.targets_json,
          updated_at = now()
        """,
        [tid, json.dumps(m.manifest, ensure_ascii=False)],
    )


def _apply_audit(con: duckdb.DuckDBPyConnection, delta: LoopStateDelta) -> None:
    m = delta.audit_mutation()
    con.execute(
        """
        INSERT INTO harness_core.loop_runs (run_id, tenant_id, distance_vector, actions_json, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (run_id) DO UPDATE SET
          distance_vector = excluded.distance_vector,
          actions_json = excluded.actions_json,
          status = excluded.status,
          created_at = now()
        """,
        [
            m.run_id,
            str(delta.tenant_id or "default"),
            json.dumps(m.distance_vector, ensure_ascii=False),
            json.dumps(m.actions_json, ensure_ascii=False),
            m.status,
        ],
    )


def _sync_handle_loop_state_delta(message: str) -> None:
    try:
        data = json.loads(message)
        delta = LoopStateDelta.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("MEDITATE_STATE_DELTA invalid payload: %s", exc)
        return

    tenant_id = str(delta.tenant_id or "default").strip() or "default"
    user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()

    if not target_db_path:
        logger.warning("MEDITATE_STATE_DELTA rejected: empty target_db_path")
        return
    if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
        logger.warning("MEDITATE_STATE_DELTA rejected: invalid db_path for user")
        return

    try:
        from duckclaw import DuckClaw
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        if path_is_under_shared_tree(target_db_path):
            acl_path = get_gateway_db_path()
            acl_con = DuckClaw(acl_path, read_only=True)
            try:
                ok_grant = user_may_access_shared_path(
                    acl_con,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    shared_db_path=target_db_path,
                )
            finally:
                try:
                    acl_con.close()
                except Exception:
                    pass
            if not ok_grant:
                logger.warning("MEDITATE_STATE_DELTA rejected: no shared grant")
                return
    except Exception as exc:  # noqa: BLE001
        logger.warning("MEDITATE_STATE_DELTA ACL shared check skipped/failed: %s", exc)

    con = _connect_duckdb_writable(target_db_path)
    try:
        _ensure_harness_schema(con)
        if delta.delta_type == "PURGE_STALE_TASKS":
            _apply_purge_stale(con, delta)
        elif delta.delta_type == "QUARANTINE_MEMORY":
            _apply_quarantine(con, delta)
        elif delta.delta_type in ("UPSERT_LOOP_AUDIT", "UPSERT_MEDITATE_AUDIT"):
            _apply_audit(con, delta)
        elif delta.delta_type == "UPSERT_HOMEOSTASIS_MANIFEST":
            _apply_manifest(con, delta)
        else:
            logger.warning("MEDITATE_STATE_DELTA unknown type: %s", delta.delta_type)
            return
        logger.info(
            "MEDITATE_STATE_DELTA ok type=%s path=%s",
            delta.delta_type,
            target_db_path,
        )
    finally:
        con.close()


async def handle_loop_state_delta_message(redis_client: Any, message: str) -> None:
    qname = str(settings.LOOP_STATE_DELTA_QUEUE_NAME).strip()
    try:
        await asyncio.to_thread(_sync_handle_loop_state_delta, message)
    except Exception as exc:  # noqa: BLE001
        # Vault RW held by gateway for whole tool rounds — requeue, do not DLQ.
        if _is_duckdb_lock_error(exc):
            logger.error(
                "MEDITATE_STATE_DELTA DuckDB lock tras reintentos; reencolando en %s: %s",
                qname,
                exc,
            )
            if redis_client is not None:
                try:
                    # RPUSH: BRPOP consumes right; avoid starving behind LPUSH backlog.
                    await redis_client.rpush(qname, message)
                except Exception as rq_exc:  # noqa: BLE001
                    logger.error("MEDITATE_STATE_DELTA reencolado falló: %s", rq_exc)
                    await push_dlq(
                        redis_client,
                        source_queue=qname,
                        message=message,
                        error=f"lock requeue failed: {rq_exc}; orig={exc}",
                        handler="loop_state_delta",
                    )
            return
        logger.exception("MEDITATE_STATE_DELTA unrecoverable: %s", exc)
        await push_dlq(
            redis_client,
            source_queue=qname,
            message=message,
            error=str(exc),
            handler="loop_state_delta",
        )
