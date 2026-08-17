"""Lite in-process session store for spawn/desktop auth."""

from __future__ import annotations

import asyncio


def test_lite_session_store_setex_get_delete() -> None:
    from duckclaw.lite_session_store import LITE_SESSION_STORE

    async def _run() -> None:
        await LITE_SESSION_STORE.setex("sess:test", 60, '{"email":"a@b.c"}')
        assert await LITE_SESSION_STORE.get("sess:test") == '{"email":"a@b.c"}'
        await LITE_SESSION_STORE.delete("sess:test")
        assert await LITE_SESSION_STORE.get("sess:test") is None

    asyncio.run(_run())


def test_lite_session_store_conversation_index() -> None:
    from duckclaw.lite_session_store import LITE_SESSION_STORE

    async def _run() -> None:
        meta_key = "duckclaw:admin:conv:meta:default:admin-conv-abc"
        zkey = "duckclaw:admin:conv:z:default"
        await LITE_SESSION_STORE.set(meta_key, '{"session_id":"admin-conv-abc"}', ex=3600)
        await LITE_SESSION_STORE.zadd(zkey, {"admin-conv-abc": 1000.0})
        assert await LITE_SESSION_STORE.get(meta_key) == '{"session_id":"admin-conv-abc"}'
        listed = await LITE_SESSION_STORE.zrevrange(zkey, 0, -1)
        assert listed == ["admin-conv-abc"]
        await LITE_SESSION_STORE.zrem(zkey, "admin-conv-abc")
        await LITE_SESSION_STORE.delete(meta_key)
        assert await LITE_SESSION_STORE.zrevrange(zkey, 0, -1) == []

    asyncio.run(_run())


def test_lite_session_store_lock_acquire_release() -> None:
    from duckclaw.lite_session_store import LITE_SESSION_STORE

    async def _run() -> None:
        lock = LITE_SESSION_STORE.lock("lock:chat:test", timeout=5, blocking_timeout=1)
        assert await lock.acquire() is True
        await lock.release()
        assert await lock.acquire() is True
        await lock.release()

    asyncio.run(_run())


def test_lite_session_store_pubsub_deliver_message() -> None:
    """Admin tool heartbeats need in-process pub/sub when Redis is omitted."""
    from duckclaw.lite_session_store import LiteSessionStore

    store = LiteSessionStore()

    async def _run() -> None:
        channel = "duckclaw:admin-heartbeat:admin-conv-test"
        pubsub = store.pubsub()
        await pubsub.subscribe(channel)
        n = store.publish(channel, '{"text":"🔄 Usando: inspect_schema","kind":"tool"}')
        assert n == 1
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        assert msg is not None
        assert msg["type"] == "message"
        assert "inspect_schema" in str(msg["data"])
        await pubsub.aclose()

    asyncio.run(_run())
