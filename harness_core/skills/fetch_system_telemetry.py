"""Read-only DuckDB telemetry sweep for meditate homeostasis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from duckclaw.duckdb_read_compat import duckclaw_open_for_read_scan

from harness_core.states.meditate_state import CurrentMetrics, HomeostasisTarget

_log = logging.getLogger(__name__)

_BACKOFF_SECONDS = (0.5, 1.0, 2.0)


def _is_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _table_exists(db: Any, qualified: str) -> bool:
    parts = qualified.split(".", 1)
    table = parts[1] if len(parts) == 2 else parts[0]
    schema = parts[0] if len(parts) == 2 else None
    table_esc = table.replace("'", "''")
    if schema:
        schema_esc = schema.replace("'", "''")
        sql = (
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema = '{schema_esc}' AND table_name = '{table_esc}' LIMIT 1"
        )
    else:
        sql = (
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table_esc}' LIMIT 1"
        )
    try:
        raw = db.query(sql)
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows:
            return True
    except Exception:
        pass
    # DuckDB: tablas sin esquema explícito viven en main
    if not schema:
        try:
            raw = db.query(f"SELECT 1 FROM main.{table} LIMIT 0")
            _ = raw
            return True
        except Exception:
            return False
    return False


def _column_exists(db: Any, qualified: str, column: str) -> bool:
    parts = qualified.split(".", 1)
    schema = parts[0] if len(parts) == 2 else "main"
    table = parts[1] if len(parts) == 2 else parts[0]
    try:
        raw = db.query(f"PRAGMA table_info('{schema}.{table}')")
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        cols = {str(r.get("name") or "") for r in rows if isinstance(r, dict)}
        return column in cols
    except Exception:
        return False


def _query_scalar(db: Any, sql: str, default: float | int = 0) -> float | int:
    raw = db.query(sql)
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if not rows:
        return default
    row = rows[0]
    if isinstance(row, dict):
        val = next(iter(row.values()), default)
    else:
        val = row[0] if row else default
    try:
        return float(val) if isinstance(default, float) else int(val)
    except (TypeError, ValueError):
        return default


def _audit_metrics(db: Any, *, tenant_id: str, window_seconds: int) -> tuple[float, float]:
    if not _table_exists(db, "task_audit_log"):
        return 0.0, 0.0
    window = max(1, int(window_seconds))
    tenant_esc = str(tenant_id).replace("'", "''")
    total = _query_scalar(
        db,
        f"""
        SELECT COUNT(*) AS c FROM task_audit_log
        WHERE tenant_id = '{tenant_esc}'
          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '{window} seconds'
        """,
        0,
    )
    failed = _query_scalar(
        db,
        f"""
        SELECT COUNT(*) AS c FROM task_audit_log
        WHERE tenant_id = '{tenant_esc}'
          AND status = 'FAILED'
          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '{window} seconds'
        """,
        0,
    )
    err_rate = (float(failed) / float(total) * 100.0) if int(total) > 0 else 0.0
    avg_lat = _query_scalar(
        db,
        f"""
        SELECT COALESCE(AVG(duration_ms), 0) AS v FROM task_audit_log
        WHERE tenant_id = '{tenant_esc}'
          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '{window} seconds'
        """,
        0.0,
    )
    return err_rate, float(avg_lat)


def _stale_tasks(
    db: Any,
    *,
    sources: list[str],
    stale_ids_out: list[str],
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_s = cutoff.isoformat()
    total = 0
    for qualified in sources:
        q = (qualified or "").strip()
        if not q or not _table_exists(db, q):
            continue
        status_col = "status" if _column_exists(db, q, "status") else None
        updated_col = "updated_at" if _column_exists(db, q, "updated_at") else None
        if not status_col or not updated_col:
            continue
        id_col = "signal_id" if _column_exists(db, q, "signal_id") else "id"
        if not _column_exists(db, q, id_col):
            continue
        sql = (
            f"SELECT CAST({id_col} AS VARCHAR) AS rid FROM {q} "
            f"WHERE {status_col} IN ('PENDING', 'ACTIVE', 'PENDING_HITL') "
            f"AND {updated_col} < TIMESTAMP '{cutoff_s}' LIMIT 200"
        )
        try:
            raw = db.query(sql)
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception as exc:
            _log.debug("stale scan skip %s: %s", q, exc)
            continue
        for row in rows or []:
            rid = ""
            if isinstance(row, dict):
                rid = str(row.get("rid") or "").strip()
            elif row:
                rid = str(row[0]).strip()
            if rid:
                stale_ids_out.append(rid)
        total += len(rows or [])
    return total


def _memory_fragmentation(db: Any, *, memory_ids_out: list[str]) -> float:
    if not _table_exists(db, "main.semantic_memory"):
        return 0.0
    pending = _query_scalar(
        db,
        "SELECT COUNT(*) FROM main.semantic_memory WHERE embedding_status = 'PENDING'",
        0,
    )
    total = _query_scalar(db, "SELECT COUNT(*) FROM main.semantic_memory", 0)
    if int(total) <= 0:
        return 0.0
    try:
        raw = db.query(
            "SELECT CAST(id AS VARCHAR) AS rid FROM main.semantic_memory "
            "WHERE embedding_status = 'PENDING' LIMIT 200"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        for row in rows or []:
            if isinstance(row, dict):
                rid = str(row.get("rid") or "").strip()
            else:
                rid = str(row[0]).strip() if row else ""
            if rid:
                memory_ids_out.append(rid)
    except Exception:
        pass
    return float(pending) / float(total)


def fetch_system_telemetry(
    vault_db_path: str,
    *,
    tenant_id: str,
    delta_interval_seconds: int,
    targets: HomeostasisTarget | dict[str, Any] | None = None,
) -> tuple[CurrentMetrics, list[str], list[str], int]:
    """
    RO multi-table sweep with exponential backoff on DuckDB lock errors.

    Returns (metrics, stale_task_ids, memory_ids_to_quarantine, db_lock_events).
    Raises on persistent lock failure after retries.
    """
    tgt = (
        targets
        if isinstance(targets, HomeostasisTarget)
        else HomeostasisTarget.model_validate(targets or {})
    )
    stale_ids: list[str] = []
    memory_ids: list[str] = []
    lock_events = 0
    last_exc: BaseException | None = None

    for attempt, delay in enumerate(_BACKOFF_SECONDS):
        try:
            with duckclaw_open_for_read_scan(vault_db_path) as db:
                err_rate, avg_lat = _audit_metrics(
                    db, tenant_id=tenant_id, window_seconds=delta_interval_seconds
                )
                stale_count = _stale_tasks(db, sources=tgt.stale_task_sources, stale_ids_out=stale_ids)
                frag = _memory_fragmentation(db, memory_ids_out=memory_ids)
                return (
                    CurrentMetrics(
                        error_rate_pct=err_rate,
                        avg_latency_ms=avg_lat,
                        stale_tasks_count=stale_count,
                        memory_fragmentation_index=frag,
                        db_lock_events=lock_events,
                    ),
                    stale_ids,
                    memory_ids,
                    lock_events,
                )
        except Exception as exc:
            last_exc = exc
            if _is_lock_error(exc):
                lock_events += 1
                if attempt + 1 < len(_BACKOFF_SECONDS):
                    time.sleep(delay)
                    continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fetch_system_telemetry: unexpected exit")
