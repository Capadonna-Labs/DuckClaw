"""Crons admin page lists /crons chat schedules (agent_config), not only PM2 cron jobs."""

from __future__ import annotations

import json

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()


def test_chat_schedules_lists_clock_prompt_and_interval(tmp_path, monkeypatch) -> None:
    import duckdb

    from duckclaw.runtime.scheduling.cron_wall_schedule import parse_cron_wall_tokens
    from routers.admin_domains import crons as crons_router

    spec, _ = parse_cron_wall_tokens(["every", "09:00", "dom"])
    spec["prompt"] = "/defense_watch"
    db_path = str(tmp_path / "vault.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT)")
    con.execute(
        "INSERT INTO agent_config VALUES (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_admin-conv-1_goals_cron_wall", json.dumps(spec),
            "chat_admin-conv-1_goals_proactive_last_fire_epoch", "1790000000.5",
            "chat_42_goals_delta_seconds", "1800",
            "chat_43_goals_delta_seconds", "0",
        ],
    )
    con.close()
    monkeypatch.setattr("duckclaw.gateway_db.iter_goals_ticker_duckdb_paths", lambda: [db_path])

    out = {s["chat_id"]: s for s in crons_router._load_chat_schedules()}
    assert set(out) == {"admin-conv-1", "42"}
    assert out["admin-conv-1"]["prompt"] == "/defense_watch" and out["admin-conv-1"]["kind"] == "reloj"
    assert out["admin-conv-1"]["last_fire_epoch"] == 1790000000.5
    assert out["42"]["schedule"] == "Cada 30 min" and out["42"]["prompt"] == "Revisión de /goals"
