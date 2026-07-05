"""Env knobs for DuckClaw-Knowledge-Indexer throughput and backpressure."""

from __future__ import annotations

import os


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def knowledge_embed_batch_size() -> int:
    """Chunks per embedding batch (sentence-transformers / MLX HTTP)."""
    return _env_int("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", 32, minimum=1, maximum=256)


def knowledge_indexer_max_inflight() -> int:
    """Max concurrent knowledge sync jobs in the indexer process."""
    return _env_int("DUCKCLAW_KNOWLEDGE_INDEXER_MAX_INFLIGHT", 1, minimum=1, maximum=8)


def knowledge_queue_depth_warn_threshold() -> int:
    """Log a warning when Redis LLEN exceeds this depth."""
    return _env_int("DUCKCLAW_KNOWLEDGE_QUEUE_DEPTH_WARN", 10, minimum=1, maximum=100_000)
