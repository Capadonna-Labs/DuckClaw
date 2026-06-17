"""LLM and media usage log typed write handlers."""

from __future__ import annotations

from typing import Any

from duckclaw.write_handlers.registry import register_handler

_LLM_USAGE_TABLE = "llm_usage_log"
_MEDIA_USAGE_TABLE = "media_usage_log"


def _llm_usage_log_ddl() -> str:
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


def _media_usage_log_ddl() -> str:
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


def _apply_append_llm_usage_log(conn: Any, payload: dict) -> None:
    conn.execute(_llm_usage_log_ddl())
    row_id = str(payload.get("id") or "").strip()
    if not row_id:
        raise ValueError("id required")
    tenant_id = str(payload.get("tenant_id") or "default").strip()[:128] or "default"
    session_id = str(payload.get("session_id") or "").strip()[:128]
    worker_id = str(payload.get("worker_id") or "").strip()[:64]
    model = str(payload.get("model") or "").strip()[:128]
    input_tokens = max(0, int(payload.get("input_tokens") or 0))
    output_tokens = max(0, int(payload.get("output_tokens") or 0))
    total_tokens = max(0, int(payload.get("total_tokens") or 0))
    cost_usd = float(payload.get("cost_usd") or 0.0)
    conn.execute(
        f"""
        INSERT INTO {_LLM_USAGE_TABLE}
          (id, tenant_id, session_id, worker_id, input_tokens, output_tokens, total_tokens, cost_usd, model)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row_id,
            tenant_id,
            session_id,
            worker_id,
            input_tokens,
            output_tokens,
            total_tokens,
            cost_usd,
            model,
        ],
    )


def _apply_append_media_usage_log(conn: Any, payload: dict) -> None:
    conn.execute(_media_usage_log_ddl())
    row_id = str(payload.get("id") or "").strip()
    if not row_id:
        raise ValueError("id required")
    tenant_id = str(payload.get("tenant_id") or "default").strip()[:128] or "default"
    session_id = str(payload.get("session_id") or "").strip()[:128]
    worker_id = str(payload.get("worker_id") or "").strip()[:64]
    provider = str(payload.get("provider") or "fal").strip()[:32] or "fal"
    model_endpoint = str(payload.get("model_endpoint") or "").strip()[:256]
    media_type = str(payload.get("media_type") or "image").strip()[:32] or "image"
    media_url = str(payload.get("media_url") or "").split("?")[0].strip()[:2048]
    cost_usd = round(float(payload.get("cost_usd") or 0.0), 6)
    latency_sec = round(float(payload.get("latency_sec") or 0.0), 3)
    conn.execute(
        f"""
        INSERT INTO {_MEDIA_USAGE_TABLE}
          (id, tenant_id, session_id, worker_id, provider, model_endpoint,
           media_type, cost_usd, latency_sec, media_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row_id,
            tenant_id,
            session_id,
            worker_id,
            provider,
            model_endpoint,
            media_type,
            cost_usd,
            latency_sec,
            media_url,
        ],
    )


register_handler("append_llm_usage_log", _apply_append_llm_usage_log)
register_handler("append_media_usage_log", _apply_append_media_usage_log)
