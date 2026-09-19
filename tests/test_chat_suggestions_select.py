"""Tests for the Redis-backed suggestion cache used by /chat/suggestions/select."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from routers.admin_domains.chat_suggestions import (
    _cache_suggestions,
    _notify_suggestions_ready,
    _read_cached_suggestions,
)
from routers.admin_domains.playground.chat_turn import _suggestion_selected_prefix


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None, nx=False):  # noqa: ANN001
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

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


def test_suggestions_push_cooldown_dedupes_rapid_calls(monkeypatch) -> None:
    """Regression: the frontend calls /chat/suggestions 2-3x per turn — only one push."""
    import duckclaw.web_push as web_push

    send_calls: list[list[str]] = []

    def _fake_list_subs(db_path):  # noqa: ANN001
        return [{"endpoint": "https://push.example/ep", "keys": {"p256dh": "x", "auth": "y"}}]

    def _fake_send(subs, **kwargs):  # noqa: ANN001
        send_calls.append(subs)
        return web_push.WebPushDeliveryResult(sent=len(subs))

    monkeypatch.setattr(web_push, "list_web_push_subscriptions", _fake_list_subs)
    monkeypatch.setattr(web_push, "send_web_push_notifications", _fake_send)
    monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: "/tmp/fake.duckdb")

    redis = _FakeRedis()

    async def _run():
        await _notify_suggestions_ready(redis, "chat-1", ["a", "b", "c"])
        await _notify_suggestions_ready(redis, "chat-1", ["a", "b", "c"])
        await _notify_suggestions_ready(redis, "chat-1", ["a", "b", "c"])

    asyncio.run(_run())
    assert len(send_calls) == 1


def test_suggestions_push_cooldown_is_per_chat_id(monkeypatch) -> None:
    import duckclaw.web_push as web_push

    send_calls: list[list[str]] = []

    monkeypatch.setattr(
        web_push,
        "list_web_push_subscriptions",
        lambda db_path: [{"endpoint": "https://push.example/ep", "keys": {"p256dh": "x", "auth": "y"}}],
    )
    monkeypatch.setattr(
        web_push,
        "send_web_push_notifications",
        lambda subs, **kwargs: send_calls.append(subs) or web_push.WebPushDeliveryResult(sent=len(subs)),
    )
    monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: "/tmp/fake.duckdb")

    redis = _FakeRedis()

    async def _run():
        await _notify_suggestions_ready(redis, "chat-1", ["a", "b", "c"])
        await _notify_suggestions_ready(redis, "chat-2", ["a", "b", "c"])

    asyncio.run(_run())
    assert len(send_calls) == 2


def test_suggestion_selected_prefix_matches_cached_option() -> None:
    redis = _FakeRedis()

    async def _run():
        await _cache_suggestions(redis, "chat-1", "tenant-a", ["Sí, documentalo", "No por ahora", "Priorízalo"])
        return await _suggestion_selected_prefix(redis, "chat-1", "  no por ahora  ")

    assert asyncio.run(_run()) == "Opción 2 seleccionada automáticamente.\n"


def test_suggestion_selected_prefix_empty_when_no_match() -> None:
    redis = _FakeRedis()

    async def _run():
        await _cache_suggestions(redis, "chat-1", "tenant-a", ["a", "b", "c"])
        return await _suggestion_selected_prefix(redis, "chat-1", "algo que el usuario escribió a mano")

    assert asyncio.run(_run()) == ""


def test_suggestion_selected_prefix_empty_without_cache_or_message() -> None:
    redis = _FakeRedis()
    assert asyncio.run(_suggestion_selected_prefix(redis, "never-cached", "hola")) == ""
    assert asyncio.run(_suggestion_selected_prefix(redis, "chat-1", "")) == ""
    assert asyncio.run(_suggestion_selected_prefix(None, "chat-1", "hola")) == ""
