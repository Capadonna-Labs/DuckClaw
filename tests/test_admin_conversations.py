"""Tests índice de conversaciones admin (Redis)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.admin_conversations import (
    AdminConversationMeta,
    derive_section_from_session_id,
    delete_conversation,
    get_conversation_meta,
    list_conversations,
    new_admin_conversation_session_id,
    patch_conversation_title,
    should_index_admin_conversation,
    upsert_conversation_meta,
)


def test_should_index_admin_conversation():
    assert should_index_admin_conversation("admin-playground")
    assert should_index_admin_conversation("admin-section-kanban")
    assert should_index_admin_conversation(new_admin_conversation_session_id())
    assert not should_index_admin_conversation("1726618406")


def test_derive_section_from_session_id():
    assert derive_section_from_session_id("admin-playground") == "playground"
    assert derive_section_from_session_id("admin-section-kanban") == "kanban"
    assert derive_section_from_session_id("admin-section-vnc") == "vnc"
    assert derive_section_from_session_id("admin-conv-abc", origin_section="playground") == "playground"
    assert derive_section_from_session_id("admin-conv-abc") == ""


async def _test_upsert_and_list_conversations_impl():
    store: dict[str, str | dict] = {}
    zset: dict[str, float] = {}

    async def mock_get(key):
        val = store.get(key)
        if val is None:
            return None
        return val if isinstance(val, bytes) else val.encode() if isinstance(val, str) else val

    async def mock_set(key, val, ex=None):
        store[key] = val

    async def mock_zadd(key, mapping):
        zset.update(mapping)

    async def mock_expire(key, ttl):
        pass

    async def mock_zrevrange(key, start, end):
        return sorted(zset.keys(), key=lambda k: zset[k], reverse=True)

    async def mock_delete(*keys):
        for k in keys:
            store.pop(k, None)
            zset.pop(k, None)

    async def mock_zrem(key, member):
        zset.pop(member, None)

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.zadd = AsyncMock(side_effect=mock_zadd)
    redis.expire = AsyncMock(side_effect=mock_expire)
    redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)
    redis.delete = AsyncMock(side_effect=mock_delete)
    redis.zrem = AsyncMock(side_effect=mock_zrem)

    sid = new_admin_conversation_session_id()
    meta = await upsert_conversation_meta(
        redis,
        tenant_id="Finanzas",
        session_id=sid,
        actor="admin@duckclaw.local",
        section="playground",
        last_worker_id="Quant-Trader",
        user_message="hola macro",
        assistant_message="resumen macro",
    )
    assert meta is not None
    assert meta.title == "hola macro"
    assert meta.section == "playground"
    assert "Quant-Trader" in meta.workers

    items, total = await list_conversations(redis, "Finanzas", section="playground")
    assert total >= 1
    assert any(i.session_id == sid for i in items)

    patched = await patch_conversation_title(redis, "Finanzas", sid, "Macro test")
    assert patched is not None
    assert patched.title == "Macro test"

    ok = await delete_conversation(redis, "Finanzas", sid)
    assert ok is True
    assert await get_conversation_meta(redis, "Finanzas", sid) is None


def test_upsert_and_list_conversations():
    import asyncio

    asyncio.run(_test_upsert_and_list_conversations_impl())


def build_fake_redis():
    """Redis mínimo en memoria para tests de integración admin."""
    store: dict[str, str] = {}
    zsets: dict[str, dict[str, float]] = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, val, ex=None):
        store[key] = val

    async def mock_zadd(key, mapping):
        zsets.setdefault(key, {}).update(mapping)

    async def mock_expire(key, ttl):
        pass

    async def mock_zrevrange(key, start, end):
        z = zsets.get(key, {})
        return sorted(z.keys(), key=lambda k: z[k], reverse=True)

    async def mock_delete(*keys):
        for k in keys:
            store.pop(k, None)
            if k in zsets:
                zsets.pop(k, None)

    async def mock_zrem(key, member):
        zsets.get(key, {}).pop(member, None)

    async def mock_scan(cursor=0, match=None, count=100):
        prefix = (match or "").replace("*", "")
        keys = [k for k in store if k.startswith(prefix)]
        return 0, keys

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.zadd = AsyncMock(side_effect=mock_zadd)
    redis.expire = AsyncMock(side_effect=mock_expire)
    redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)
    redis.delete = AsyncMock(side_effect=mock_delete)
    redis.zrem = AsyncMock(side_effect=mock_zrem)
    redis.scan = AsyncMock(side_effect=mock_scan)
    return redis


def test_admin_conversation_meta_roundtrip():
    m = AdminConversationMeta(
        session_id="admin-conv-1",
        tenant_id="default",
        title="Test",
        workers=["finanz"],
        preferred_worker_id="finanz",
    )
    data = json.loads(m.model_dump_json())
    restored = AdminConversationMeta.model_validate(data)
    assert restored.title == "Test"
    assert restored.preferred_worker_id == "finanz"


async def _test_patch_conversation_worker_impl():
    from core.admin_conversations import patch_conversation_worker

    redis = build_fake_redis()
    sid = new_admin_conversation_session_id()
    await upsert_conversation_meta(
        redis,
        tenant_id="default",
        session_id=sid,
        last_worker_id="default",
        title="Worker test",
    )
    meta = await patch_conversation_worker(redis, "default", sid, "finanz")
    assert meta is not None
    assert meta.preferred_worker_id == "finanz"
    assert "finanz" in meta.workers


def test_patch_conversation_worker():
    import asyncio

    asyncio.run(_test_patch_conversation_worker_impl())
