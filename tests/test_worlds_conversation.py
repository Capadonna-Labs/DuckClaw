"""Worlds conversation: the owner talks to a bot from the playground (inbox) and the runner publishes the dialogue. Redis and the chat store are replaced by recorders."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

H = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
RUNNER = {"X-Worlds-Runner-Key": "runner-key", "X-Duckclaw-Actor": "admin@test.local"}


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:]

    async def expire(self, key, ttl):
        return True

    async def lpop(self, key):
        items = self.lists.get(key) or []
        return items.pop(0) if items else None


@pytest.fixture
def api(admin_client: TestClient, gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import core.admin_conversations as conv
    import core.chat_history as hist
    from duckclaw.write_command_handlers import registered_handlers
    from routers.admin_domains import worlds

    def apply(command) -> str:
        payload = json.loads(command.model_dump_json())
        con = duckdb.connect(str(gateway_db))
        try:
            registered_handlers()[payload["command_type"]](con, payload)
        finally:
            con.close()
        return payload["task_id"]

    store: dict[str, list] = {}
    metas: list[dict] = []

    async def load(redis_client, tenant, sid):
        return list(store.get((tenant, sid), []))

    async def save(redis_client, tenant, sid, items):
        store[(tenant, sid)] = list(items)

    async def meta(redis_client, **kw):
        metas.append(kw)

    monkeypatch.setenv("DUCKCLAW_WORLDS_RUNNER_KEY", "runner-key")
    monkeypatch.setattr(worlds, "_enqueue", apply)
    monkeypatch.setattr(hist, "redis_load_chat_history", load)
    monkeypatch.setattr(hist, "redis_save_chat_history", save)
    monkeypatch.setattr(conv, "upsert_conversation_meta", meta)
    admin_client.app.state.redis = FakeRedis()
    admin_client.store, admin_client.metas = store, metas  # type: ignore[attr-defined]
    return admin_client


def _bot(api: TestClient) -> str:
    wid = api.post("/api/v1/admin/worlds", headers=H, json={"name": "W"}).json()["world_id"]
    return api.post("/api/v1/admin/worlds/bots", headers=H, json={"world_id": wid, "name": "b"}).json()["bot_id"]


def test_what_the_owner_says_reaches_the_inbox_once_and_shows_in_the_conversation(api: TestClient) -> None:
    bid = _bot(api)
    r = api.post("/api/v1/admin/worlds/bots/say", headers=H, json={"bot_id": bid, "text": "  ven   acá  "})
    assert r.status_code == 200, r.text
    sid = r.json()["conversation_id"]
    assert sid.startswith("admin-conv-") and all(c in "0123456789abcdef" for c in sid[len("admin-conv-"):])        # the shape the playground indexes
    first = api.get(f"/api/v1/admin/worlds/bots/inbox?bot_id={bid}", headers=RUNNER).json()
    assert [m["text"] for m in first["messages"]] == ["ven acá"] and first["conversation_id"] == sid
    assert api.get(f"/api/v1/admin/worlds/bots/inbox?bot_id={bid}", headers=RUNNER).json()["messages"] == []          # delivered once
    assert [(i["role"], i["content"]) for i in next(iter(api.store.values()))] == [("user", "ven acá")]               # type: ignore[attr-defined]
    assert api.metas[-1]["session_id"] == sid and api.metas[-1]["message_count"] == 1                                  # type: ignore[attr-defined]


def test_the_runner_publishes_the_dialogue_but_cannot_put_words_in_the_inbox(api: TestClient) -> None:
    bid = _bot(api)
    r = api.post("/api/v1/admin/worlds/bots/transcript", headers=RUNNER, json={"bot_id": bid, "items": [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡hola!"}]})
    assert r.status_code == 200 and r.json()["messages"] == 2
    assert api.post("/api/v1/admin/worlds/bots/say", headers=RUNNER, json={"bot_id": bid, "text": "x"}).status_code in (401, 403)     # say is the admin's
    assert api.get(f"/api/v1/admin/worlds/bots/inbox?bot_id={bid}", headers=RUNNER).json()["messages"] == []


def test_unknown_bot_and_oversized_text(api: TestClient) -> None:
    assert api.post("/api/v1/admin/worlds/bots/say", headers=H, json={"bot_id": "nope", "text": "x"}).status_code == 404
    bid = _bot(api)
    assert api.post("/api/v1/admin/worlds/bots/say", headers=H, json={"bot_id": bid, "text": "x" * 501}).status_code == 422


def test_the_module_stays_generic_and_registered() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    assert "router.include_router(worlds_conversation_router)" in admin
    src = Path("services/api-gateway/routers/admin_domains/worlds_conversation.py").read_text(encoding="utf-8").lower()
    assert "minecraft" not in src and "capadonna" not in src
