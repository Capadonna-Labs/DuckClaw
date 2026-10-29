"""Worlds think: a runner sends a deliberate turn to the worker named in the bot's own settings. The chat itself is replaced by a recorder."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from fastapi.testclient import TestClient

H = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
OTHER = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "other@test.local"}


@pytest.fixture
def api(admin_client: TestClient, gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from duckclaw.write_command_handlers import registered_handlers
    from routers.admin_domains import worlds, worlds_think
    from routers.admin_domains.playground import chat_turn

    def apply(command) -> str:
        payload = json.loads(command.model_dump_json())
        con = duckdb.connect(str(gateway_db))
        try:
            registered_handlers()[payload["command_type"]](con, payload)
        finally:
            con.close()
        return payload["task_id"]

    seen: list[dict] = []

    async def prepare(body, *, actor, request, **_):
        seen.append({"worker_id": body.worker_id, "message": body.message, "chat_id": body.chat_id, "tenant_id": body.tenant_id, "actor": actor})
        return SimpleNamespace(wid=body.worker_id)

    async def invoke(prepared, *, request):
        return {"response": f"<say>hola</say> from {prepared.wid}", "usage_tokens": 42}

    monkeypatch.setattr(worlds, "_enqueue", apply)
    monkeypatch.setattr(chat_turn, "prepare_playground_chat_turn", prepare)
    monkeypatch.setattr(chat_turn, "invoke_playground_chat_sync", invoke)
    monkeypatch.setattr(chat_turn, "format_playground_chat_payload", lambda prepared, result: {"response": result["response"], "usage_tokens": result["usage_tokens"]})
    worlds_think._CALLS.clear()
    admin_client.seen = seen  # type: ignore[attr-defined]
    return admin_client


def _bot(api: TestClient, settings: dict | None = None, **extra) -> str:
    wid = api.post("/api/v1/admin/worlds", headers=H, json={"name": "W"}).json()["world_id"]
    return api.post("/api/v1/admin/worlds/bots", headers=H, json={"world_id": wid, "name": "b", "settings": settings or {}, **extra}).json()["bot_id"]


def test_a_turn_runs_on_the_worker_in_the_bots_settings(api: TestClient) -> None:
    bid = _bot(api, {"planner_worker": "planner-1"})
    r = api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": bid, "message": "¿qué hago ahora?"})
    assert r.status_code == 200, r.text
    assert r.json()["response"] == "<say>hola</say> from planner-1" and r.json()["worker_id"] == "planner-1" and r.json()["usage_tokens"] == 42
    got = api.seen[-1]  # type: ignore[attr-defined]
    assert got["worker_id"] == "planner-1" and got["message"] == "¿qué hago ahora?" and got["actor"] == "admin@test.local"
    assert got["chat_id"] == f"world-{bid}"                               # one conversation per bot unless the runner names its own


def test_the_worker_is_never_the_callers_choice_and_must_be_configured(api: TestClient) -> None:
    bare = _bot(api)
    assert api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": bare, "message": "x"}).status_code == 409          # no planner_worker
    weird = _bot(api, {"planner_worker": "../../etc"})
    assert api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": weird, "message": "x"}).status_code == 409          # not a worker id
    ok = _bot(api, {"planner_worker": "p"})
    r = api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": ok, "message": "x", "worker_id": "admin-worker"})       # extra field ignored
    assert r.status_code == 200 and api.seen[-1]["worker_id"] == "p"  # type: ignore[attr-defined]


def test_scoping_disabled_and_unknown_bots(api: TestClient) -> None:
    bid = _bot(api, {"planner_worker": "p"})
    assert api.post("/api/v1/admin/worlds/think", headers=OTHER, json={"bot_id": bid, "message": "x"}).status_code == 404          # another owner
    assert api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": "nope", "message": "x"}).status_code == 404
    api.patch("/api/v1/admin/worlds/bots", headers=H, json={"id": bid, "enabled": False})
    assert api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": bid, "message": "x"}).status_code == 409
    assert api.post("/api/v1/admin/worlds/think", json={"bot_id": bid, "message": "x"}).status_code in (401, 403, 422)             # no key


def test_each_bot_is_capped_per_minute(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORLD_THINK_PER_MIN", "2")
    a, b = _bot(api, {"planner_worker": "p"}), _bot(api, {"planner_worker": "p"})
    codes = [api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": a, "message": "x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert api.post("/api/v1/admin/worlds/think", headers=H, json={"bot_id": b, "message": "x"}).status_code == 200                # the cap is per bot


def test_the_runner_key_reaches_think_and_nothing_else_new(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORLDS_RUNNER_KEY", "runner-secret")
    R = {"X-Worlds-Runner-Key": "runner-secret", "X-Duckclaw-Actor": "admin@test.local"}
    bid = _bot(api, {"planner_worker": "p"})
    assert api.post("/api/v1/admin/worlds/think", headers=R, json={"bot_id": bid, "message": "x"}).status_code == 200
    assert api.post("/api/v1/admin/playground/chat", headers=R, json={"worker_id": "p", "message": "x"}).status_code in (401, 403)   # not the whole playground


def test_the_module_stays_generic_and_registered() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    assert "router.include_router(worlds_think_router)" in admin
    src = Path("services/api-gateway/routers/admin_domains/worlds_think.py").read_text(encoding="utf-8").lower()
    assert "minecraft" not in src and "insert" not in src and "update " not in src
