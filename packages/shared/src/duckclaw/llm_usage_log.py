"""Persistencia y estimación de costo LLM (tokens + USD) en la DuckDB del gateway."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Mapping

_LLM_USAGE_TABLE = "llm_usage_log"


def _skip_runtime_ddl(db: Any) -> bool:
    return bool(getattr(db, "_read_only", False))


def estimate_llm_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    model: str | None = None,
) -> float:
    """Estima USD por millón de tokens (rates configurables vía env)."""
    _ = model
    try:
        in_rate = float(os.environ.get("DUCKCLAW_LLM_COST_INPUT_USD_PER_M") or "0.15")
    except (TypeError, ValueError):
        in_rate = 0.15
    try:
        out_rate = float(os.environ.get("DUCKCLAW_LLM_COST_OUTPUT_USD_PER_M") or "0.60")
    except (TypeError, ValueError):
        out_rate = 0.60
    return (max(0, input_tokens) / 1_000_000.0 * in_rate) + (
        max(0, output_tokens) / 1_000_000.0 * out_rate
    )


def normalize_usage_tokens(usage: Mapping[str, Any]) -> tuple[int, int, int]:
    inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (inp + out))
    return max(0, inp), max(0, out), max(0, total)


def _llm_usage_log_ddl_sql() -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {_LLM_USAGE_TABLE} (
            id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            session_id VARCHAR,
            worker_id VARCHAR,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd DOUBLE NOT NULL DEFAULT 0,
            model VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """


def ensure_llm_usage_log_table(db: Any) -> None:
    """Crea la tabla en RW directo o vía db-writer cuando el gateway usa DuckDB RO."""
    ddl = _llm_usage_log_ddl_sql()
    if _skip_runtime_ddl(db):
        try:
            _enqueue_write(db, ddl, "default")
        except Exception:
            pass
        return
    db.execute(ddl)


def _infer_user_id_for_queue(db_path: str) -> str:
    from pathlib import Path

    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _enqueue_write(db: Any, sql: str, tenant_id: str) -> None:
    from pathlib import Path

    from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return
    resolved = str(Path(raw_path).expanduser().resolve())
    uid = _infer_user_id_for_queue(resolved)
    released_ro = False
    try:
        release = getattr(db, "release_file_handle_for_external_writer", None)
        susp = getattr(db, "suspend_readonly_file_handle", None)
        resu = getattr(db, "resume_readonly_file_handle", None)
        if callable(release):
            release()
            released_ro = bool(callable(resu))
        elif callable(susp) and callable(resu):
            susp()
            released_ro = True
        write_tid = enqueue_duckdb_write_sync(
            db_path=resolved,
            query=sql.strip(),
            user_id=uid,
            tenant_id=str(tenant_id or "default").strip() or "default",
        )
        poll_task_status_sync(write_tid, timeout_sec=15.0)
    finally:
        if released_ro:
            try:
                resu2 = getattr(db, "resume_readonly_file_handle", None)
                if callable(resu2):
                    resu2()
            except Exception:
                pass


def append_llm_usage_log(
    db: Any,
    *,
    tenant_id: str,
    session_id: str | None,
    worker_id: str | None,
    usage: Mapping[str, Any],
    model: str | None = None,
) -> None:
    """Registra un turno de chat con tokens y costo estimado."""
    if not usage:
        return
    inp, out, total = normalize_usage_tokens(usage)
    if total <= 0 and inp <= 0 and out <= 0:
        return

    ensure_llm_usage_log_table(db)
    row_id = f"USAGE-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    cost = round(estimate_llm_cost_usd(inp, out, model=model), 6)
    tenant_s = str(tenant_id or "default").replace("'", "''")[:128]
    session_s = str(session_id or "").replace("'", "''")[:128]
    worker_s = str(worker_id or "").replace("'", "''")[:64]
    model_s = str(model or "").replace("'", "''")[:128]
    sql = (
        f"""
        INSERT INTO {_LLM_USAGE_TABLE}
          (id, tenant_id, session_id, worker_id, input_tokens, output_tokens, total_tokens, cost_usd, model)
        VALUES (
          '{row_id}', '{tenant_s}', '{session_s}', '{worker_s}',
          {inp}, {out}, {total}, {cost}, '{model_s}'
        )
        """
    )
    if _skip_runtime_ddl(db):
        try:
            _enqueue_write(db, sql, tenant_s)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("llm_usage_log: enqueue insert failed: %s", exc)
        return
    db.execute(sql)
