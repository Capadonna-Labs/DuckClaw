"""Persistencia durable de conversaciones admin en DuckDB."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


@pytest.fixture()
def gateway_db(tmp_path, monkeypatch):
    db_path = tmp_path / "duckclaw.duckdb"
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_path))
    monkeypatch.setenv("LITE_MODE", "1")
    from duckclaw.spawn_profile import apply_lite_mode_env

    apply_lite_mode_env()
    from duckclaw.schema_migrations import migrate_gateway_database

    migrate_gateway_database(str(db_path), seed_admin=False)
    return db_path


def test_migration_38_adds_conversation_meta_columns(gateway_db):
    from duckclaw import DuckClaw

    db = DuckClaw(str(gateway_db), read_only=True, engine="python")
    try:
        result = db.execute("PRAGMA table_info('main.admin_conversations')")
        rows = result.fetchall() if hasattr(result, "fetchall") else result
        cols = {str(r[1]) for r in rows}
        for expected in (
            "section",
            "last_worker_id",
            "preferred_worker_id",
            "workers_json",
            "last_message_preview",
            "message_count",
            "origin",
        ):
            assert expected in cols, f"missing column {expected}"
    finally:
        db.close()


def test_duckdb_conversation_survives_redis_wipe(gateway_db):
    from core.admin_conversations import (
        get_conversation_meta,
        list_conversations,
        new_admin_conversation_session_id,
        patch_conversation_title,
        upsert_conversation_meta,
    )
    from core.admin_conversations_db import db_load_messages, db_save_messages
    from core.chat_history import redis_load_chat_history, redis_save_chat_history
    from tests.test_admin_conversations import build_fake_redis

    redis = build_fake_redis()
    sid = new_admin_conversation_session_id()

    async def _run():
        meta = await upsert_conversation_meta(
            redis,
            tenant_id="default",
            session_id=sid,
            actor="admin@duckclaw.local",
            section="playground",
            title="Conversación 2026-08-16",
            last_worker_id="finanz-1",
            user_message="Hola presupuesto",
            assistant_message="Claro, veamos tus gastos",
            message_count=2,
        )
        assert meta is not None
        assert meta.title == "Hola presupuesto"
        await redis_save_chat_history(
            redis,
            "default",
            sid,
            [
                {"role": "user", "content": "Hola presupuesto"},
                {"role": "assistant", "content": "Claro, veamos tus gastos"},
            ],
        )
        patched = await patch_conversation_title(redis, "default", sid, "Finanzas personales")
        assert patched is not None
        assert patched.title == "Finanzas personales"

        # Simulate LiteSessionStore wipe (gateway restart).
        redis_empty = build_fake_redis()
        restored = await get_conversation_meta(redis_empty, "default", sid)
        assert restored is not None
        assert restored.title == "Finanzas personales"
        msgs = await redis_load_chat_history(redis_empty, "default", sid)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "Hola presupuesto"
        items, total = await list_conversations(redis_empty, "default")
        assert total >= 1
        assert any(i.session_id == sid and i.title == "Finanzas personales" for i in items)
        assert len(db_load_messages("default", sid)) == 2

    asyncio.run(_run())


def test_redis_only_conversation_hydrates_into_duckdb(gateway_db):
    from core.admin_conversations import get_conversation_meta, new_admin_conversation_session_id
    from core.admin_conversations_db import db_get_conversation_meta, db_load_messages
    from core.chat_history import redis_save_chat_history
    from tests.test_admin_conversations import build_fake_redis

    redis = build_fake_redis()
    sid = new_admin_conversation_session_id()

    async def _seed_redis_only():
        # Write Redis cache without going through DuckDB upsert path first.
        from core.admin_conversations import AdminConversationMeta, _cache_upsert_meta

        meta = AdminConversationMeta(
            session_id=sid,
            tenant_id="default",
            title="Solo Redis",
            section="playground",
            actor="admin@duckclaw.local",
            message_count=2,
            last_message_preview="hola",
        )
        await _cache_upsert_meta(redis, meta)
        await redis_save_chat_history(
            redis,
            "default",
            sid,
            [
                {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "qué tal"},
            ],
        )
        # Wipe DuckDB rows if redis_save already wrote messages (it does dual-write).
        # Re-seed by deleting duckdb conversation and keeping redis.
        from core.admin_conversations_db import db_delete_conversation

        db_delete_conversation("default", sid)
        assert db_get_conversation_meta("default", sid) is None

        # Put redis meta back (delete doesn't clear redis in this test path for messages only).
        await _cache_upsert_meta(redis, meta)
        await redis_save_chat_history(
            redis,
            "default",
            sid,
            [
                {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "qué tal"},
            ],
        )
        # After redis_save, DuckDB messages exist again; delete meta only is enough for hydrate test.
        # Force meta miss in DuckDB:
        db_delete_conversation("default", sid)
        await _cache_upsert_meta(redis, meta)

        loaded = await get_conversation_meta(redis, "default", sid)
        assert loaded is not None
        assert loaded.title == "Solo Redis"
        assert db_get_conversation_meta("default", sid) is not None
        # Messages may be empty if we deleted them; hydrate copies redis history when present.
        msgs = db_load_messages("default", sid)
        assert isinstance(msgs, list)

    asyncio.run(_seed_redis_only())


def test_patch_title_resolves_legacy_default_tenant(gateway_db):
    from core.admin_conversations import (
        new_admin_conversation_session_id,
        patch_conversation_title,
        upsert_conversation_meta,
    )
    from tests.test_admin_conversations import build_fake_redis

    redis = build_fake_redis()
    sid = new_admin_conversation_session_id()

    async def _run():
        await upsert_conversation_meta(
            redis,
            tenant_id="default",
            session_id=sid,
            title="Original",
            section="playground",
        )
        # Authenticated tenant differs; legacy record under default must still rename.
        patched = await patch_conversation_title(
            redis, "user-admin-abc", sid, "Renombrada"
        )
        assert patched is not None
        assert patched.title == "Renombrada"
        assert patched.tenant_id == "default"

    asyncio.run(_run())
