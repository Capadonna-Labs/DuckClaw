from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from routers.admin_domains.admin_common import require_admin_key as _require_admin_key_impl

router = APIRouter(tags=["admin-overview"])


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    _require_admin_key_impl(x_admin_key)


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _templates_dir() -> Any:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def gateway_db_query_rows(db: Any, sql: str) -> list[dict[str, Any]]:
    """Parse JSON rows from GatewayDbEphemeralReadonly.query."""
    try:
        raw = db.query(sql)
    except Exception:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
    elif isinstance(raw, list):
        parsed = raw
    else:
        return []
    if not isinstance(parsed, list):
        return []
    return [r for r in parsed if isinstance(r, dict)]


def overview_usage_metrics(
    db: Any,
    *,
    days: int = 7,
    group_by: str = "worker",
    worker_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Agregados de tokens/USD desde llm_usage_log (tabla opcional)."""
    days_clamped = max(1, min(int(days or 7), 90))
    group = (group_by or "worker").strip().lower()
    if group not in ("worker", "day", "session"):
        group = "worker"

    wid_filter = (worker_id or "").strip().replace("'", "''")
    sid_filter = (session_id or "").strip().replace("'", "''")
    where_parts = [f"created_at >= now() - INTERVAL '{days_clamped} days'"]
    if wid_filter:
        where_parts.append(f"worker_id = '{wid_filter}'")
    if sid_filter:
        where_parts.append(f"session_id = '{sid_filter}'")
    where_sql = " AND ".join(where_parts)

    empty: dict[str, Any] = {
        "summary": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        },
        "series": [],
        "filters": {
            "days": days_clamped,
            "group_by": group,
            "worker_id": wid_filter or None,
            "session_id": sid_filter or None,
        },
        "workers": [],
        "sessions": [],
    }

    try:
        db.query("SELECT 1 FROM main.llm_usage_log LIMIT 1")
    except Exception:
        return empty

    if group == "day":
        series_sql = f"""
            SELECT strftime(created_at, '%Y-%m-%d') AS label,
                   NULL AS worker_id,
                   NULL AS session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
            GROUP BY label
            ORDER BY label
        """
    elif group == "session":
        series_sql = f"""
            SELECT coalesce(session_id, '(sin id)') AS label,
                   max(worker_id) AS worker_id,
                   session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
              AND session_id IS NOT NULL AND trim(session_id) != ''
            GROUP BY session_id
            ORDER BY total_tokens DESC
            LIMIT 40
        """
    else:
        series_sql = f"""
            SELECT worker_id AS label,
                   worker_id,
                   NULL AS session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
              AND worker_id IS NOT NULL AND trim(worker_id) != ''
            GROUP BY worker_id
            ORDER BY total_tokens DESC
        """

    summary_sql = f"""
        SELECT sum(input_tokens) AS input_tokens,
               sum(output_tokens) AS output_tokens,
               sum(total_tokens) AS total_tokens,
               round(sum(cost_usd), 6) AS cost_usd
        FROM main.llm_usage_log
        WHERE {where_sql}
    """
    workers_sql = f"""
        SELECT DISTINCT worker_id
        FROM main.llm_usage_log
        WHERE created_at >= now() - INTERVAL '{days_clamped} days'
          AND worker_id IS NOT NULL AND trim(worker_id) != ''
        ORDER BY worker_id
    """
    sessions_sql = f"""
        SELECT session_id,
               max(worker_id) AS worker_id,
               sum(total_tokens) AS total_tokens,
               round(sum(cost_usd), 6) AS cost_usd
        FROM main.llm_usage_log
        WHERE created_at >= now() - INTERVAL '{days_clamped} days'
          AND session_id IS NOT NULL AND trim(session_id) != ''
        GROUP BY session_id
        ORDER BY total_tokens DESC
        LIMIT 30
    """

    summary_rows = gateway_db_query_rows(db, summary_sql)
    series_rows = gateway_db_query_rows(db, series_sql)
    worker_rows = gateway_db_query_rows(db, workers_sql)
    session_rows = gateway_db_query_rows(db, sessions_sql)

    summary_row = summary_rows[0] if summary_rows else {}
    try:
        summary = {
            "input_tokens": int(summary_row.get("input_tokens") or 0),
            "output_tokens": int(summary_row.get("output_tokens") or 0),
            "total_tokens": int(summary_row.get("total_tokens") or 0),
            "cost_usd": float(summary_row.get("cost_usd") or 0.0),
        }
    except (TypeError, ValueError):
        summary = empty["summary"]

    series: list[dict[str, Any]] = []
    for row in series_rows:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        try:
            series.append(
                {
                    "label": label,
                    "worker_id": row.get("worker_id"),
                    "session_id": row.get("session_id"),
                    "input_tokens": int(row.get("input_tokens") or 0),
                    "output_tokens": int(row.get("output_tokens") or 0),
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "cost_usd": float(row.get("cost_usd") or 0.0),
                }
            )
        except (TypeError, ValueError):
            continue

    workers = [
        str(r.get("worker_id") or "").strip()
        for r in worker_rows
        if str(r.get("worker_id") or "").strip()
    ]
    sessions: list[dict[str, Any]] = []
    for row in session_rows:
        sid = str(row.get("session_id") or "").strip()
        if not sid:
            continue
        try:
            sessions.append(
                {
                    "session_id": sid,
                    "worker_id": row.get("worker_id"),
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "cost_usd": float(row.get("cost_usd") or 0.0),
                }
            )
        except (TypeError, ValueError):
            continue

    return {
        "summary": summary,
        "series": series,
        "filters": empty["filters"],
        "workers": workers,
        "sessions": sessions,
    }


@router.get("/health", dependencies=[Depends(require_admin_key)])
async def admin_health(request: Request) -> dict[str, Any]:
    workers: list[str] = []
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_worker_catalog import list_visible_workers_for_actor
        from duckclaw.workers.factory import list_workers

        with open_gateway_db(read_only=True) as db:
            actor = (request.headers.get("x-duckclaw-actor") or "").strip().lower()
            if actor and "@" in actor:
                workers = [
                    str(item.get("id") or item.get("worker_id") or "").strip()
                    for item in list_visible_workers_for_actor(db, actor_email=actor)
                    if str(item.get("id") or item.get("worker_id") or "").strip()
                ]
            else:
                workers = list_workers(db=db)
    except Exception:
        workers = []
    redis_ok = False
    try:
        r = getattr(request.app.state, "redis", None)
        if r is not None:
            await r.ping()
            redis_ok = True
    except Exception:
        redis_ok = False

    gateway_metrics: dict[str, Any] = {}
    try:
        from duckclaw.ops.gateway_health_metrics import collect_gateway_health_metrics

        gateway_metrics = collect_gateway_health_metrics()
    except Exception:
        gateway_metrics = {}

    return {
        "status": "ok",
        "workers_count": len(workers),
        "workers": workers[:20],
        "redis": redis_ok,
        "templates_dir": str(_templates_dir()),
        "api_revision": 2,
        "features": {
            "catalog": True,
            "ops": True,
            "projects": True,
        },
        "gateway_metrics": gateway_metrics,
    }


@router.get("/overview/metrics", dependencies=[Depends(require_admin_key)])
async def admin_overview_metrics(
    usage_days: int = 7,
    usage_group_by: str = "worker",
    worker_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Agregados analíticos: uso LLM (tokens/USD), actividad 7d y latencia 24h."""
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw or "missing")

    db = GatewayDbEphemeralReadonly(gw)
    usage = overview_usage_metrics(
        db,
        days=usage_days,
        group_by=usage_group_by,
        worker_id=worker_id,
        session_id=session_id,
    )
    activity_sql = """
        SELECT worker_id,
               COUNT(*) FILTER (WHERE upper(status) = 'SUCCESS') AS success_count,
               COUNT(*) FILTER (WHERE upper(status) = 'FAILED') AS failed_count
        FROM main.task_audit_log
        WHERE created_at >= now() - INTERVAL '7 days'
          AND worker_id IS NOT NULL AND trim(worker_id) != ''
        GROUP BY worker_id
        ORDER BY worker_id
    """
    latency_sql = """
        SELECT strftime(created_at, '%H:00') AS hour,
               round(avg(duration_ms)) AS avg_latency
        FROM main.task_audit_log
        WHERE created_at >= now() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY cast(left(hour, 2) AS INTEGER)
    """
    activity_rows = gateway_db_query_rows(db, activity_sql)
    latency_rows = gateway_db_query_rows(db, latency_sql)

    activity: list[dict[str, Any]] = []
    for row in activity_rows:
        wid = str(row.get("worker_id") or "").strip()
        if not wid:
            continue
        try:
            success_count = int(row.get("success_count") or 0)
        except (TypeError, ValueError):
            success_count = 0
        try:
            failed_count = int(row.get("failed_count") or 0)
        except (TypeError, ValueError):
            failed_count = 0
        activity.append(
            {
                "worker_id": wid,
                "success_count": success_count,
                "failed_count": failed_count,
            }
        )

    latency: list[dict[str, Any]] = []
    for row in latency_rows:
        hour = str(row.get("hour") or "").strip()
        if not hour:
            continue
        try:
            avg_latency = int(row.get("avg_latency") or 0)
        except (TypeError, ValueError):
            avg_latency = 0
        latency.append({"hour": hour, "avg_latency": avg_latency})

    return {"usage": usage, "activity": activity, "latency": latency, "db_path": gw}
