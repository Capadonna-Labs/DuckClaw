"""Tests for the Redis-backed suggestion cache used by /chat/suggestions/select."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from routers.admin_domains.chat_suggestions import _cache_suggestions, _read_cached_suggestions


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):  # noqa: ANN001
        self.store[key] = value

    async def get(self, key):  # noqa: ANN001
        return self.store.get(key)


def test_cache_round_trip() -> None:
    redis = _FakeRedis()

    async def _run():
        await _cache_suggestions(redis, "chat-1", "tenant-a", ["opt a", "opt b", "opt c"])
        return await _read_cached_suggestions(redis, "chat-1")

    cached = asyncio.run(_run())
    assert cached == {"tenant_id": "tenant-a", "suggestions": ["opt a", "opt b", "opt c"]}


def test_cache_skips_empty_suggestions() -> None:
    redis = _FakeRedis()

    async def _run():
        await _cache_suggestions(redis, "chat-1", "tenant-a", [])
        return await _read_cached_suggestions(redis, "chat-1")

    assert asyncio.run(_run()) is None


def test_read_missing_key_returns_none() -> None:
    redis = _FakeRedis()
    assert asyncio.run(_read_cached_suggestions(redis, "never-cached")) is None


def test_read_with_no_redis_client_returns_none() -> None:
    assert asyncio.run(_read_cached_suggestions(None, "chat-1")) is None


def test_cache_write_swallows_redis_errors() -> None:
    class _BrokenRedis:
        async def set(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("redis down")

    # Should not raise — this runs as a fire-and-forget background task.
    asyncio.run(_cache_suggestions(_BrokenRedis(), "chat-1", "tenant-a", ["x"]))
