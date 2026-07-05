"""Process role boundaries — Gateway must stay I/O-bound; workers own schedulers and ingest."""

from __future__ import annotations

import os

_ROLE_GATEWAY = "gateway"
_ROLE_KNOWLEDGE_INDEXER = "knowledge-indexer"
_ROLE_HEARTBEAT = "heartbeat"
_ROLE_DB_WRITER = "db-writer"


def process_role() -> str:
    explicit = (os.environ.get("DUCKCLAW_PROCESS_ROLE") or "").strip().lower()
    if explicit:
        return explicit
    pm2_name = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip().lower()
    if "knowledge-indexer" in pm2_name or "knowledge_indexer" in pm2_name:
        return _ROLE_KNOWLEDGE_INDEXER
    if "heartbeat" in pm2_name:
        return _ROLE_HEARTBEAT
    if "db-writer" in pm2_name or "db_writer" in pm2_name:
        return _ROLE_DB_WRITER
    return _ROLE_GATEWAY


def is_gateway_process() -> bool:
    return process_role() == _ROLE_GATEWAY


def is_knowledge_indexer_process() -> bool:
    return process_role() == _ROLE_KNOWLEDGE_INDEXER


def embed_goals_ticker_in_gateway() -> bool:
    """Crons/méditate ticker belongs in DuckClaw-Heartbeat, not the HTTP gateway."""
    raw = (os.environ.get("DUCKCLAW_EMBED_GOALS_TICKER") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def embed_knowledge_sync_in_gateway() -> bool:
    """Legacy dev escape hatch — production should use DuckClaw-Knowledge-Indexer."""
    raw = (os.environ.get("DUCKCLAW_GATEWAY_EMBED_KNOWLEDGE_SYNC") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def gateway_embedding_policy() -> str:
    """
    ``remote_only`` (default): Gateway never loads sentence-transformers locally.
    ``allow_local``: dev-only fallback when MLX embeddings URL is unset.
    """
    return (os.environ.get("DUCKCLAW_GATEWAY_EMBEDDING_POLICY") or "remote_only").strip().lower()
