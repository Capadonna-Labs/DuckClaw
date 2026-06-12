"""Ingesta CUSTOM_REPORT_UPSERT: DDL + upsert en main.custom_reports + pub/sub reload."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import duckdb

from core.config import settings
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import resolve_user_id_for_db_path
from models.reports_state_delta import ReportsStateDelta

logger = logging.getLogger("db-writer.reports_state_delta")

REPORT_UPDATE_CHANNEL_PREFIX = "duckclaw:report-update:"

_CUSTOM_REPORTS_DDL = """
CREATE TABLE IF NOT EXISTS main.custom_reports (
  report_id VARCHAR(100) PRIMARY KEY,
  title VARCHAR(200) NOT NULL DEFAULT 'Reporte',
  html_content TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_by VARCHAR(200),
  updated_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_custom_reports_id ON main.custom_reports(report_id);
"""


def report_update_channel(report_id: str) -> str:
    rid = str(report_id or "").strip() or "unknown"
    return f"{REPORT_UPDATE_CHANNEL_PREFIX}{rid}"


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _connect_duckdb_writable(
    path: str,
    *,
    attempts: int = 12,
    base_sleep_s: float = 0.25,
) -> duckdb.DuckDBPyConnection:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_duckdb_lock_error(exc) and i < attempts - 1:
                time.sleep(base_sleep_s * (i + 1))
                continue
            raise
    if last is not None:
        raise last
    raise RuntimeError("connect duckdb failed")


def _ensure_custom_reports_schema(con: duckdb.DuckDBPyConnection) -> None:
    for stmt in _CUSTOM_REPORTS_DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)


def _apply_custom_report_upsert(con: duckdb.DuckDBPyConnection, delta: ReportsStateDelta) -> None:
    _ensure_custom_reports_schema(con)
    m = delta.mutation
    con.execute(
        """
        INSERT INTO main.custom_reports (
          report_id, title, html_content, version, created_by
        ) VALUES (?, ?, ?, 1, ?)
        ON CONFLICT (report_id) DO UPDATE SET
          title = excluded.title,
          html_content = excluded.html_content,
          version = main.custom_reports.version + 1,
          created_by = CASE
            WHEN trim(excluded.created_by) != '' THEN excluded.created_by
            ELSE main.custom_reports.created_by
          END,
          updated_at = now()
        """,
        [
            m.report_id,
            m.title or "Reporte",
            m.html_content,
            m.created_by or "",
        ],
    )


def _publish_report_reload(report_id: str) -> None:
    url = (os.environ.get("REDIS_URL") or str(settings.REDIS_URL) or "").strip()
    if not url:
        logger.warning("REPORTS_STATE_DELTA: REDIS_URL ausente; omitiendo publish reload")
        return
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.publish(report_update_channel(report_id), "reload")
    except Exception as exc:  # noqa: BLE001
        logger.warning("REPORTS_STATE_DELTA publish failed report_id=%s: %s", report_id, exc)


def _sync_handle_reports_state_delta(message: str) -> None:
    try:
        data = json.loads(message)
        delta = ReportsStateDelta.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("REPORTS_STATE_DELTA invalid payload: %s", exc)
        return

    tenant_id = str(delta.tenant_id or "default").strip() or "default"
    raw_user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()

    if not target_db_path:
        logger.warning("REPORTS_STATE_DELTA rejected: empty target_db_path")
        return
    resolved_uid = resolve_user_id_for_db_path(raw_user_id, target_db_path, tenant_id=tenant_id)
    if resolved_uid is None:
        logger.warning(
            "REPORTS_STATE_DELTA rejected: invalid db_path for user raw_user_id=%s path=%s",
            raw_user_id,
            target_db_path[-120:],
        )
        return
    user_id = resolved_uid

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
                logger.warning("REPORTS_STATE_DELTA rejected: no shared grant")
                return
    except Exception as exc:  # noqa: BLE001
        logger.warning("REPORTS_STATE_DELTA ACL shared check skipped/failed: %s", exc)

    con = _connect_duckdb_writable(target_db_path)
    try:
        _apply_custom_report_upsert(con, delta)
        logger.info(
            "CUSTOM_REPORT_UPSERT report_id=%s db=%s",
            delta.mutation.report_id,
            target_db_path,
        )
        # region agent log
        try:
            import time
            from pathlib import Path

            _dbg = {
                "sessionId": "97f3cb",
                "hypothesisId": "H4",
                "location": "reports_state_delta_handler.py",
                "message": "custom_report_upsert_ok",
                "data": {
                    "report_id": delta.mutation.report_id,
                    "vault": target_db_path[-120:],
                },
                "timestamp": int(time.time() * 1000),
            }
            for _k in ("DUCKCLAW_REPO_ROOT", "CAPADONNA_DRILLER_ROOT"):
                _r = (os.environ.get(_k) or "").strip()
                if _r:
                    try:
                        (Path(_r) / "debug-97f3cb.log").open("a", encoding="utf-8").write(
                            json.dumps(_dbg, ensure_ascii=False) + "\n"
                        )
                        break
                    except OSError:
                        pass
        except Exception:
            pass
        # endregion
    finally:
        con.close()

    _publish_report_reload(delta.mutation.report_id)


async def handle_reports_state_delta_message(redis_client: Any, message: str) -> None:
    del redis_client
    await asyncio.to_thread(_sync_handle_reports_state_delta, message)
