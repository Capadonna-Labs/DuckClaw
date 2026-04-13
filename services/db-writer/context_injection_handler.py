"""Ingesta CONTEXT_INJECTION: DDL, chunking, embeddings, inserts DuckDB."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, List

import duckdb

from core.config import settings
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import validate_user_db_path
from models.context_injection import ContextInjectionStateDelta

logger = logging.getLogger("db-writer.context_injection")

MAX_CHUNK_CHARS = 8000

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


def chunk_context_raw_text(raw: str, max_chunk: int = MAX_CHUNK_CHARS) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if len(text) <= max_chunk:
        return [text]
    chunks: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if not p:
            continue
        if len(p) <= max_chunk:
            chunks.append(p)
            continue
        buf = ""
        for line in p.split("\n"):
            candidate = f"{buf}\n{line}".strip() if buf else line
            if len(candidate) > max_chunk:
                if buf:
                    chunks.append(buf.strip())
                    buf = line
                else:
                    buf = line
                while len(buf) > max_chunk:
                    chunks.append(buf[:max_chunk])
                    buf = buf[max_chunk:]
                continue
            buf = candidate
        if buf.strip():
            chunks.append(buf.strip())
    return [c for c in chunks if c]


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _connect_duckdb_writable(
    path: str,
    *,
    attempts: int = 12,
    base_sleep_s: float = 0.25,
) -> duckdb.DuckDBPyConnection:
    """
    Abre DuckDB en escritura con reintentos ante lock (p. ej. gateway con RO abierto).
    Tras agotar intentos, relanza la última excepción para que el caller pueda reencolar.
    """
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_duckdb_lock_error(exc):
                delay = base_sleep_s * min(i + 1, 8)
                logger.warning(
                    "CONTEXT_INJECTION DuckDB lock intento %s/%s, reintento en %.2fs: %s",
                    i + 1,
                    attempts,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


def _embed_chunk(text: str) -> tuple[list[float] | None, bool]:
    """
    Retorna (vector | None, computed_ok).
    computed_ok False = modelo ausente o error; True = vector válido 384-dim.
    """
    try:
        from duckclaw.forge.rag.embeddings import embed_text

        vec = embed_text(text)
        if vec is None:
            return None, False
        if len(vec) != 384:
            logger.warning("embedding dim=%s expected 384", len(vec))
            return None, False
        return vec, True
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding failed: %s", exc)
        return None, False


def _needs_embedding_queue_key() -> str:
    return str(settings.NEEDS_EMBEDDING_QUEUE_NAME or "duckclaw:needs_embedding").strip()


async def _publish_needs_embedding(
    redis_client: Any,
    *,
    row_id: str,
    target_db_path: str,
    content_preview: str,
    user_id: str,
    tenant_id: str,
) -> None:
    if redis_client is None:
        return
    payload = {
        "event": "NEEDS_EMBEDDING",
        "row_id": row_id,
        "target_db_path": target_db_path,
        "content_preview": (content_preview or "")[:2000],
        "user_id": user_id,
        "tenant_id": tenant_id,
    }
    try:
        await redis_client.lpush(_needs_embedding_queue_key(), json.dumps(payload, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        logger.warning("NEEDS_EMBEDDING LPUSH failed: %s", exc)


def _insert_row(
    con: duckdb.DuckDBPyConnection,
    *,
    row_id: str,
    content: str,
    source: str,
    embedding: List[float] | None,
    embedding_status: str,
) -> None:
    con.execute(
        """
        INSERT INTO main.semantic_memory (id, content, source, embedding, embedding_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        [row_id, content, source, embedding, embedding_status],
    )


def _sync_handle_context_injection(message: str) -> list[dict[str, Any]]:
    """
    Procesa el mensaje JSON. Devuelve eventos NEEDS_EMBEDDING para publicar en async.
    """
    try:
        data = json.loads(message)
        delta = ContextInjectionStateDelta.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.error("CONTEXT_INJECTION invalid payload: %s", exc)
        return []

    tenant_id = str(delta.tenant_id or "default").strip() or "default"
    user_id = str(delta.user_id or "default").strip() or "default"
    target_db_path = str(delta.target_db_path or "").strip()

    if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
        logger.warning("CONTEXT_INJECTION rejected: invalid db_path for user")
        return []

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
                logger.warning("CONTEXT_INJECTION rejected: no shared grant")
                return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("CONTEXT_INJECTION ACL shared check skipped/failed: %s", exc)

    raw = delta.mutation.raw_text
    source_col = str(delta.mutation.source or "telegram_cmd").strip() or "telegram_cmd"
    parts = chunk_context_raw_text(raw)
    if not parts:
        logger.warning("CONTEXT_INJECTION empty after chunking")
        return []

    logger.info(
        "Insertando contexto en DB. Longitud raw=%s caracteres, chunks=%s, db=%s",
        len(raw),
        len(parts),
        target_db_path,
    )

    needs_events: list[dict[str, Any]] = []
    # Cerrar la conexión tras cada chunk: el embedding puede tardar (modelo); sin bloquear
    # el archivo mientras el gateway u otros procesos necesitan RO.
    for chunk in parts:
        row_id = str(uuid.uuid4())
        emb: list[float] | None = None
        emb_ok = False
        try:
            emb, emb_ok = _embed_chunk(chunk)
        except Exception as emb_exc:  # noqa: BLE001
            logger.warning(
                "CONTEXT_INJECTION embedding error (se inserta texto sin vector): %s",
                emb_exc,
            )
            emb, emb_ok = None, False

        inserted = False
        con = _connect_duckdb_writable(target_db_path)
        try:
            con.execute(_SEMANTIC_MEMORY_DDL)
            if emb_ok and emb is not None:
                try:
                    _insert_row(
                        con,
                        row_id=row_id,
                        content=chunk,
                        source=source_col,
                        embedding=emb,
                        embedding_status="READY",
                    )
                    inserted = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "CONTEXT_INJECTION INSERT con embedding falló, reintento con NULL: %s",
                        exc,
                    )

            if not inserted:
                try:
                    _insert_row(
                        con,
                        row_id=row_id,
                        content=chunk,
                        source=source_col,
                        embedding=None,
                        embedding_status="FAILED",
                    )
                except Exception as ins_exc:  # noqa: BLE001
                    logger.error(
                        "CONTEXT_INJECTION INSERT falló incluso sin embedding (chunk len=%s): %s",
                        len(chunk),
                        ins_exc,
                    )
                    raise
                needs_events.append(
                    {
                        "row_id": row_id,
                        "target_db_path": target_db_path,
                        "content_preview": chunk,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                    }
                )
        finally:
            con.close()

    logger.info("CONTEXT_INJECTION almacenó %s chunks en %s", len(parts), target_db_path)
    return needs_events


async def handle_context_injection_message(redis_client: Any, message: str) -> None:
    qname = str(settings.CONTEXT_INJECTION_QUEUE_NAME).strip()
    try:
        events = await asyncio.to_thread(_sync_handle_context_injection, message)
    except Exception as exc:  # noqa: BLE001
        if _is_duckdb_lock_error(exc):
            logger.error(
                "CONTEXT_INJECTION DuckDB bloqueado tras reintentos; reencolando en %s: %s",
                qname,
                exc,
            )
            if redis_client is not None:
                try:
                    # RPUSH al final: BRPOP consume por la derecha; así el reintento no queda
                    # detrás de todo el backlog LPUSH del gateway.
                    await redis_client.rpush(qname, message)
                except Exception as rq_exc:  # noqa: BLE001
                    logger.error("CONTEXT_INJECTION reencolado falló: %s", rq_exc)
            return
        logger.exception("CONTEXT_INJECTION error procesando mensaje: %s", exc)
        return

    for ev in events:
        await _publish_needs_embedding(redis_client, **ev)
