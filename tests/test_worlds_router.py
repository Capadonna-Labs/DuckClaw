"""Worlds admin API: configure worlds and bots, read them back with the runner's status. Writes go through the (here synchronous) typed-command queue."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

H = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
OTHER = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "other@test.local"}


@pytest.fixture
def api(admin_client: TestClient, gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The real router with the queue replaced by a direct call of the registered handler on the gateway DB."""
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

    monkeypatch.setattr(worlds, "_enqueue", apply)
    return admin_client


def test_create_list_update_delete_a_world_with_bots(api: TestClient) -> None:
    r = api.post("/api/v1/admin/worlds", headers=H, json={"name": "Casa", "host": "100.99.72.63", "port": 25565, "config": {"edition": "java", "plugins": ["geyser"]}})
    assert r.status_code == 200, r.text
    wid = r.json()["world_id"]

    b = api.post("/api/v1/admin/worlds/bots", headers=H, json={"world_id": wid, "name": "Capadonna", "settings": {"model": "m", "max_tokens": 600}})
    assert b.status_code == 200, b.text
    bid = b.json()["bot_id"]

    worlds = api.get("/api/v1/admin/worlds", headers=H).json()["worlds"]
    assert [w["name"] for w in worlds] == ["Casa"] and worlds[0]["config"]["plugins"] == ["geyser"] and worlds[0]["port"] == 25565
    assert [(x["name"], x["status"]) for x in worlds[0]["bots"]] == [("Capadonna", "unknown")]

    assert api.patch("/api/v1/admin/worlds", headers=H, json={"id": wid, "name": "Casa 2", "enabled": False}).status_code == 200
    again = api.get("/api/v1/admin/worlds", headers=H).json()["worlds"][0]
    assert (again["name"], again["enabled"], again["host"], again["port"]) == ("Casa 2", False, "100.99.72.63", 25565)   # untouched fields survive a partial edit

    assert api.patch("/api/v1/admin/worlds/bots", headers=H, json={"id": bid, "settings": {"model": "other"}}).status_code == 200
    assert api.get("/api/v1/admin/worlds", headers=H).json()["worlds"][0]["bots"][0]["settings"] == {"model": "other"}

    assert api.delete(f"/api/v1/admin/worlds/bots?id={bid}", headers=H).status_code == 200
    assert api.delete(f"/api/v1/admin/worlds?id={wid}", headers=H).status_code == 200
    assert api.get("/api/v1/admin/worlds", headers=H).json()["worlds"] == []


def test_runner_status_is_reported_and_goes_stale(api: TestClient, gateway_db: Path) -> None:
    wid = api.post("/api/v1/admin/worlds", headers=H, json={"name": "W"}).json()["world_id"]
    bid = api.post("/api/v1/admin/worlds/bots", headers=H, json={"world_id": wid, "name": "b"}).json()["bot_id"]
    assert api.post("/api/v1/admin/worlds/bots/status", headers=H, json={"bot_id": bid, "status": "online", "detail": "spawned"}).status_code == 200
    bot = api.get("/api/v1/admin/worlds", headers=H).json()["worlds"][0]["bots"][0]
    assert (bot["status"], bot["status_detail"], bot["seconds_since_report"] is not None) == ("online", "spawned", True)

    con = duckdb.connect(str(gateway_db))            # the runner went silent two minutes ago
    con.execute("UPDATE main.admin_world_bots SET last_seen_at = CAST(CURRENT_TIMESTAMP AS TIMESTAMP) - INTERVAL 120 SECOND")
    con.close()
    stale = api.get("/api/v1/admin/worlds", headers=H).json()["worlds"][0]["bots"][0]
    assert (stale["status"], stale["reported_status"]) == ("offline", "online")


def test_validation_scoping_and_auth(api: TestClient) -> None:
    assert api.post("/api/v1/admin/worlds", headers=H, json={"name": "x", "config": {"rcon_password": "p"}}).status_code == 400
    assert api.post("/api/v1/admin/worlds", headers=H, json={"name": "x", "port": 99999}).status_code == 400
    assert api.post("/api/v1/admin/worlds", headers=H, json={"config": {}}).status_code == 400            # name required
    assert api.post("/api/v1/admin/worlds/bots", headers=H, json={"world_id": "nope", "name": "b"}).status_code == 404

    wid = api.post("/api/v1/admin/worlds", headers=H, json={"name": "mine"}).json()["world_id"]
    assert api.get("/api/v1/admin/worlds", headers=OTHER).json()["worlds"] == []                           # another user sees nothing
    assert api.delete(f"/api/v1/admin/worlds?id={wid}", headers=OTHER).status_code == 404
    assert api.patch("/api/v1/admin/worlds", headers=OTHER, json={"id": wid, "name": "hijack"}).status_code == 404
    assert api.get("/api/v1/admin/worlds").status_code in (401, 403, 422)                                  # no admin key


def test_routes_live_in_their_own_domain_module_and_the_gateway_never_writes_directly() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    assert "from routers.admin_domains.worlds import router as worlds_router" in admin and "router.include_router(worlds_router)" in admin
    src = Path("services/api-gateway/routers/admin_domains/worlds.py").read_text(encoding="utf-8")
    assert "read_only=True" in src and "INSERT" not in src and "UPDATE " not in src and "DELETE FROM" not in src
