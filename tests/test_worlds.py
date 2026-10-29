"""Worlds: self-hosted worlds and bots. DuckClaw stores the config and the runner's status; secrets never go in the free-form JSON."""

from __future__ import annotations

import json

import duckdb
import pytest
from pydantic import ValidationError

from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_commands import (
    DeleteWorldBotCommand,
    DeleteWorldCommand,
    ReportWorldBotStatusCommand,
    UpsertWorldBotCommand,
    UpsertWorldCommand,
)
from duckclaw.write_handlers.worlds import (
    _apply_delete_world,
    _apply_delete_world_bot,
    _apply_report_world_bot_status,
    _apply_upsert_world,
    _apply_upsert_world_bot,
)


@pytest.fixture()
def con():
    c = duckdb.connect(":memory:")
    run_pending_migrations(c)
    return c


def payload(cmd) -> dict:
    return json.loads(cmd.model_dump_json())


def rows(c, sql: str, *params):
    return c.execute(sql, list(params)).fetchall()


def test_migration_creates_both_tables_and_is_idempotent(con) -> None:
    names = {r[0] for r in rows(con, "SELECT table_name FROM information_schema.tables WHERE table_schema='main'")}
    assert {"admin_worlds", "admin_world_bots"} <= names
    assert run_pending_migrations(con) == []            # second run applies nothing


@pytest.mark.parametrize("bad", [
    {"rcon_password": "x"}, {"RCON_PASSWORD": "x"}, {"openrouter_api_key": "x"}, {"auth": {"token": "x"}}, {"access_token": "x"}, {"auth-token": "x"},
    {"servers": [{"name": "a", "client_secret": "x"}]}, {"private-key": "x"},
])
def test_secret_looking_keys_are_refused_at_any_depth(bad) -> None:
    with pytest.raises(ValidationError, match="secret"):
        UpsertWorldCommand(name="w", config=bad)
    with pytest.raises(ValidationError, match="secret"):
        UpsertWorldBotCommand(world_id="w", name="b", settings=bad)


def test_ordinary_free_form_config_is_accepted() -> None:
    cmd = UpsertWorldCommand(name="Casa", config={"edition": "java", "version": "1.20.6", "plugins": ["geyser"], "whitelist": ["a", "b"], "tokens_per_turn": 600, "max_tokens": 800})
    assert cmd.config["plugins"] == ["geyser"]           # LLM token budgets are ordinary config, not secrets


def test_fields_are_validated() -> None:
    for kw in ({"port": 0}, {"port": 70000}, {"kind": "Minecraft!"}, {"host": "http://x"}, {"host": "a b"}, {"name": ""}, {"config": {"x": "y" * 17_000}}):
        with pytest.raises(ValidationError):
            UpsertWorldCommand(**{"name": "w", **kw})
    ok = UpsertWorldCommand(name="w", host="100.99.72.63", port=25565, kind="minecraft")  # a kind is whatever the extension calls itself
    assert (ok.host, ok.port) == ("100.99.72.63", 25565)


def test_world_and_bot_lifecycle_in_the_database(con) -> None:
    w = UpsertWorldCommand(tenant_id="t1", actor_email="a@x.com", name="Casa", host="10.0.0.5", port=25565, config={"edition": "java"})
    _apply_upsert_world(con, payload(w))
    b = UpsertWorldBotCommand(tenant_id="t1", actor_email="a@x.com", world_id=w.world_id, name="Capadonna", settings={"model": "m"})
    _apply_upsert_world_bot(con, payload(b))
    assert rows(con, "SELECT name, host, port, enabled FROM main.admin_worlds") == [("Casa", "10.0.0.5", 25565, True)]
    assert rows(con, "SELECT name, status FROM main.admin_world_bots") == [("Capadonna", "unknown")]

    _apply_report_world_bot_status(con, payload(ReportWorldBotStatusCommand(tenant_id="t1", actor_email="a@x.com", bot_id=b.bot_id, status="online", detail="spawned")))
    assert rows(con, "SELECT status, status_detail, last_seen_at IS NOT NULL FROM main.admin_world_bots") == [("online", "spawned", True)]

    # editing the bot never touches what the runner reported
    _apply_upsert_world_bot(con, payload(UpsertWorldBotCommand(tenant_id="t1", actor_email="a@x.com", bot_id=b.bot_id, world_id=w.world_id, name="Capadonna 2", enabled=False)))
    assert rows(con, "SELECT name, enabled, status FROM main.admin_world_bots") == [("Capadonna 2", False, "online")]

    _apply_delete_world(con, payload(DeleteWorldCommand(tenant_id="t1", actor_email="a@x.com", world_id=w.world_id)))
    assert rows(con, "SELECT count(*) FROM main.admin_worlds")[0][0] == 0 and rows(con, "SELECT count(*) FROM main.admin_world_bots")[0][0] == 0


def test_tenant_and_actor_scoping(con) -> None:
    w = UpsertWorldCommand(tenant_id="t1", actor_email="a@x.com", name="Casa")
    _apply_upsert_world(con, payload(w))
    b = UpsertWorldBotCommand(tenant_id="t1", actor_email="a@x.com", world_id=w.world_id, name="bot")
    _apply_upsert_world_bot(con, payload(b))
    for other in ({"tenant_id": "t2", "actor_email": "a@x.com"}, {"tenant_id": "t1", "actor_email": "evil@x.com"}):
        with pytest.raises(ValueError):
            _apply_upsert_world(con, payload(UpsertWorldCommand(world_id=w.world_id, name="hijack", **other)))
        with pytest.raises(ValueError):
            _apply_delete_world(con, payload(DeleteWorldCommand(world_id=w.world_id, **other)))
        with pytest.raises(ValueError):
            _apply_upsert_world_bot(con, payload(UpsertWorldBotCommand(bot_id=b.bot_id, world_id=w.world_id, name="hijack", **other)))
        with pytest.raises(ValueError):
            _apply_report_world_bot_status(con, payload(ReportWorldBotStatusCommand(bot_id=b.bot_id, status="online", **other)))
        with pytest.raises(ValueError):
            _apply_delete_world_bot(con, payload(DeleteWorldBotCommand(bot_id=b.bot_id, **other)))
    with pytest.raises(ValueError):   # a bot needs a world of the same owner
        _apply_upsert_world_bot(con, payload(UpsertWorldBotCommand(tenant_id="t1", actor_email="a@x.com", world_id="nope", name="x")))
    assert rows(con, "SELECT name FROM main.admin_worlds") == [("Casa",)]
