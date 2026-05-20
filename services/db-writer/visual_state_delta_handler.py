"""Ingesta VISUAL_ASSET_UPSERT: DDL + upsert en main.visual_assets."""

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
from models.visual_state_delta import VisualStateDelta

logger = logging.getLogger("db-writer.visual_state_delta")

_VISUAL_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS main.visual_assets (
  id VARCHAR PRIMARY KEY,
  prompt TEXT NOT NULL,
  negative_prompt VARCHAR DEFAULT '',
  file_path VARCHAR NOT NULL,
  aspect_ratio VARCHAR DEFAULT '1:1',
  prompt_id_comfy VARCHAR DEFAULT '',
  operation VARCHAR DEFAULT '',
  source_image_path VARCHAR DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_VISUAL_ASSETS_ALTER = [
    "ALTER TABLE main.visual_assets ADD COLUMN IF NOT EXISTS operation VARCHAR DEFAULT ''",
    "ALTER TABLE main.visual_assets ADD COLUMN IF NOT EXISTS source_image_path VARCHAR DEFAULT ''",
]


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


def _ensure_visual_assets_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_VISUAL_ASSETS_DDL)
    for stmt in _VISUAL_ASSETS_ALTER:
        try:
            con.execute(stmt)
        except Exception:
            pass


def _apply_visual_asset_upsert(con: duckdb.DuckDBPyConnection, delta: VisualStateDelta) -> None:
    _ensure_visual_assets_schema(con)
    m = delta.mutation
    con.execute(
        """
        INSERT INTO main.visual_assets (
          id, prompt, negative_prompt, file_path, aspect_ratio, prompt_id_comfy,
          operation, source_image_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
          prompt = excluded.prompt,
          negative_prompt = excluded.negative_prompt,
          file_path = excluded.file_path,
          aspect_ratio = excluded.aspect_ratio,
          prompt_id_comfy = excluded.prompt_id_comfy,
          operation = excluded.operation,
          source_image_path = excluded.source_image_path
        """,
        [
            m.id,
            m.prompt,
            m.negative_prompt or "",
            m.file_path,
            m.aspect_ratio or "1:1",
            m.prompt_id_comfy or "",
            m.operation or "",
            m.source_image_path or "",
        ],
    )


def _sync_handle_visual_state_delta(message: str) -> None:
    try:
        data = json.loads(message)
        delta = VisualStateDelta.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("VISUAL_STATE_DELTA invalid payload: %s", exc)
        return

    tenant_id = str(delta.tenant_id or "default").strip() or "default"
    user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()

    if not target_db_path:
        logger.warning("VISUAL_STATE_DELTA rejected: empty target_db_path")
        return
    if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
        logger.warning("VISUAL_STATE_DELTA rejected: invalid db_path for user")
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
                logger.warning("VISUAL_STATE_DELTA rejected: no shared grant")
                return
    except Exception as exc:  # noqa: BLE001
        logger.warning("VISUAL_STATE_DELTA ACL shared check skipped/failed: %s", exc)

    con = _connect_duckdb_writable(target_db_path)
    try:
        _apply_visual_asset_upsert(con, delta)
        logger.info(
            "VISUAL_ASSET_UPSERT id=%s db=%s",
            delta.mutation.id,
            target_db_path,
        )
    finally:
        con.close()


async def handle_visual_state_delta_message(redis_client: Any, message: str) -> None:
    del redis_client
    await asyncio.to_thread(_sync_handle_visual_state_delta, message)
