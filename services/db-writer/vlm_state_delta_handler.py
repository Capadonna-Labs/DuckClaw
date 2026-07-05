"""Persist VLM_CONTEXT_EXTRACTED into hub semantic_memory."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import duckdb

from core.config import settings
from db_writer_ops import push_dlq
from duckclaw.gateway_db import get_gateway_db_path
from models.vlm_state_delta import VlmStateDelta

logger = logging.getLogger("db-writer.vlm_state_delta")

_SEMANTIC_MEMORY_DDL = """
CREATE TABLE IF NOT EXISTS main.semantic_memory (
  id VARCHAR PRIMARY KEY,
  content TEXT NOT NULL,
  source VARCHAR DEFAULT 'manual_injection',
  embedding FLOAT[384],
  embedding_status VARCHAR DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect_hub_writable() -> duckdb.DuckDBPyConnection:
    path = (get_gateway_db_path() or "").strip()
    if not path:
        raise RuntimeError("hub db path missing")
    return duckdb.connect(path, read_only=False)


def _sync_handle_vlm_state_delta(message: str) -> None:
    try:
        data = json.loads(message)
        delta = VlmStateDelta.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("VLM_STATE_DELTA invalid payload: %s", exc)
        return

    m = delta.mutation
    row_id = f"vlm_{m.image_hash[:48]}"
    content = (
        f"[VLM_CONTEXT image_hash={m.image_hash} confidence={m.confidence_score:.2f}]\n"
        f"{m.vlm_summary.strip()}"
    )
    source = f"vlm_tenant:{delta.tenant_id}"

    con = _connect_hub_writable()
    try:
        con.execute(_SEMANTIC_MEMORY_DDL)
        con.execute(
            """
            INSERT INTO main.semantic_memory (id, content, source, embedding, embedding_status)
            VALUES (?, ?, ?, NULL, 'PENDING')
            ON CONFLICT (id) DO UPDATE SET
              content = excluded.content,
              source = excluded.source,
              embedding_status = 'PENDING'
            """,
            [row_id, content[:8000], source],
        )
        logger.info(
            "VLM_CONTEXT_EXTRACTED stored id=%s tenant=%s hash=%s",
            row_id,
            delta.tenant_id,
            m.image_hash[:16],
        )
    finally:
        con.close()


async def handle_vlm_state_delta_message(redis_client: Any, message: str) -> None:
    qname = str(settings.VLM_STATE_DELTA_QUEUE_NAME).strip()
    try:
        await asyncio.to_thread(_sync_handle_vlm_state_delta, message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("VLM_STATE_DELTA unrecoverable: %s", exc)
        await push_dlq(
            redis_client,
            source_queue=qname,
            message=message,
            error=str(exc),
            handler="vlm_state_delta",
        )
