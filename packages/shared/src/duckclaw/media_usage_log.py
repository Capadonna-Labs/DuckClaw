"""Persistencia y circuit breaker financiero para generacion multimedia (Fal.ai)."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

_MEDIA_USAGE_TABLE = "media_usage_log"

_DEFAULT_RATES: dict[str, float] = {
    "fal-ai/flux/dev": 0.025,
    "fal-ai/flux-pro/v1.1-ultra": 0.05,
    "fal-ai/kling-video/v1.6/standard/text-to-video": 0.35,
    "fal-ai/kling/v2.5/video-to-video": 0.35,
    "fal-ai/wan/v2.2-a14b/text-to-video": 0.30,
    "fal-ai/comfy": 0.05,
}


class MediaBudgetExceededError(Exception):
    """Costo diario del tenant supera el tope configurado."""


def _skip_runtime_ddl(db: Any) -> bool:
    return bool(getattr(db, "_read_only", False))


def media_daily_budget_usd() -> float:
    try:
        return float(os.environ.get("DUCKCLAW_MEDIA_DAILY_BUDGET_USD") or "2.0")
    except (TypeError, ValueError):
        return 5.0


def estimate_media_cost_usd(
    model_endpoint: str,
    *,
    media_type: str = "image",
    duration_sec: float = 5.0,
) -> float:
    ep = (model_endpoint or "").strip()
    rate = _DEFAULT_RATES.get(ep)
    if rate is None:
        slug = ep.replace("/", "_").replace("-", "_").upper()[:80]
        env_key = f"DUCKCLAW_MEDIA_RATE_{slug}"
        try:
            rate = float(os.environ.get(env_key) or "0.05")
        except (TypeError, ValueError):
            rate = 0.05
    if (media_type or "").strip().lower() == "video":
        per_sec = float(os.environ.get("DUCKCLAW_MEDIA_KLING_USD_PER_SEC") or "0.07")
        return round(max(duration_sec, 1.0) * per_sec, 6)
    return round(float(rate), 6)


def _media_usage_log_ddl_sql() -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {_MEDIA_USAGE_TABLE} (
            id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            session_id VARCHAR,
            worker_id VARCHAR,
            provider VARCHAR NOT NULL DEFAULT 'fal',
            model_endpoint VARCHAR,
            media_type VARCHAR,
            cost_usd DOUBLE NOT NULL DEFAULT 0,
            latency_sec DOUBLE NOT NULL DEFAULT 0,
            media_url VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """


def ensure_media_usage_log_table(db: Any) -> None:
    ddl = _media_usage_log_ddl_sql()
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


def sum_media_cost_usd_today(db: Any, tenant_id: str) -> float:
    ensure_media_usage_log_table(db)
    tenant_s = str(tenant_id or "default").replace("'", "''")[:128]
    sql = (
        f"SELECT COALESCE(SUM(cost_usd), 0) AS total FROM {_MEDIA_USAGE_TABLE} "
        f"WHERE tenant_id = '{tenant_s}' "
        f"AND created_at >= date_trunc('day', CURRENT_TIMESTAMP)"
    )
    try:
        r = db.query(sql)
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return float(rows[0].get("total") or 0.0)
    except Exception:
        pass
    return 0.0


def assert_media_budget_ok(
    db: Any,
    tenant_id: str,
    *,
    projected_cost_usd: float = 0.0,
) -> None:
    cap = media_daily_budget_usd()
    spent = sum_media_cost_usd_today(db, tenant_id)
    if spent + max(0.0, projected_cost_usd) > cap:
        raise MediaBudgetExceededError(
            f"Circuit breaker multimedia: gasto diario ${spent:.4f} + "
            f"proyectado ${projected_cost_usd:.4f} supera el tope ${cap:.2f} USD."
        )


def append_media_usage_log(
    db: Any,
    *,
    tenant_id: str,
    session_id: str | None,
    worker_id: str | None,
    model_endpoint: str,
    media_type: str,
    cost_usd: float,
    latency_sec: float,
    media_url: str = "",
    provider: str = "fal",
) -> None:
    ensure_media_usage_log_table(db)
    row_id = f"MEDIA-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tenant_s = str(tenant_id or "default").replace("'", "''")[:128]
    session_s = str(session_id or "").replace("'", "''")[:128]
    worker_s = str(worker_id or "").replace("'", "''")[:64]
    ep_s = str(model_endpoint or "").replace("'", "''")[:256]
    mt_s = str(media_type or "image").replace("'", "''")[:32]
    prov_s = str(provider or "fal").replace("'", "''")[:32]
    url_s = str(media_url or "").split("?")[0].replace("'", "''")[:2048]
    cost = round(float(cost_usd), 6)
    lat = round(float(latency_sec), 3)
    sql = (
        f"""
        INSERT INTO {_MEDIA_USAGE_TABLE}
          (id, tenant_id, session_id, worker_id, provider, model_endpoint,
           media_type, cost_usd, latency_sec, media_url)
        VALUES (
          '{row_id}', '{tenant_s}', '{session_s}', '{worker_s}', '{prov_s}',
          '{ep_s}', '{mt_s}', {cost}, {lat}, '{url_s}'
        )
        """
    )
    if _skip_runtime_ddl(db):
        try:
            _enqueue_write(db, sql, tenant_s)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("media_usage_log: enqueue insert failed: %s", exc)
        return
    db.execute(sql)