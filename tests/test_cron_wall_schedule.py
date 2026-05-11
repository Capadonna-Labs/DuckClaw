"""Tests unitarios para /crons --timestamp (cron_wall_schedule)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

import pytest

from duckclaw.forge.atoms.cron_wall_schedule import (
    CRON_WALL_V1,
    parse_cron_wall_tokens,
    wall_once_expired,
    wall_schedule_should_fire,
)


def test_parse_every_daily() -> None:
    spec, err = parse_cron_wall_tokens(["every", "09:30"])
    assert err is None and spec is not None
    assert spec["v"] == CRON_WALL_V1
    assert spec["kind"] == "every"
    assert spec["every_h"] == 9 and spec["every_mi"] == 30
    assert spec.get("weekdays") == []


def test_parse_every_weekdays_keyword() -> None:
    spec, err = parse_cron_wall_tokens(["every", "14:00", "weekdays"])
    assert err is None and spec is not None
    assert spec["weekdays"] == [0, 1, 2, 3, 4]


def test_parse_every_custom_days() -> None:
    spec, err = parse_cron_wall_tokens(["every", "08:00", "mon", "wed"])
    assert err is None and spec is not None
    assert spec["weekdays"] == [0, 2]


def test_wall_schedule_should_fire_every_matching_minute(monkeypatch: Any) -> None:
    tz = "America/Bogota"
    zi = ZoneInfo(tz)
    # Wednesday 2026-05-13 14:45 local — weekday() == 2
    t = datetime(2026, 5, 13, 14, 45, 0, tzinfo=zi).timestamp()
    spec = {"v": 1, "tz": tz, "kind": "every", "every_h": 14, "every_mi": 45, "weekdays": [2]}
    assert wall_schedule_should_fire(t, spec, 0.0, 45.0)
    assert not wall_schedule_should_fire(t, spec, t, 45.0)  # mismo minuto ya disparado


def test_wall_once_expired_after_slot() -> None:
    tz = "America/Bogota"
    spec = {
        "v": 1,
        "tz": tz,
        "kind": "once",
        "once_y": 2026,
        "once_mo": 5,
        "once_d": 13,
        "once_h": 10,
        "once_mi": 0,
    }
    zi = ZoneInfo(tz)
    after = datetime(2026, 5, 13, 10, 5, 0, tzinfo=zi).timestamp()
    assert wall_once_expired(spec, after)


def test_execute_goals_timestamp_every_writes_spec(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import (
        _GOALS_CRON_WALL_KEY,
        execute_goals,
        get_chat_state,
    )

    db_path = str(tmp_path / "ts.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_22_worker_id", "manager", "chat_22_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 22, "--timestamp every 15:30 weekdays", tenant_id="default")
    assert "Programación por reloj" in (out or "")
    with DuckClaw(db_path, read_only=True) as db:
        raw = (get_chat_state(db, 22, _GOALS_CRON_WALL_KEY) or "").strip()
        import json

        j = json.loads(raw)
        assert j.get("kind") == "every"
        assert j.get("weekdays") == [0, 1, 2, 3, 4]


def test_chat_id_from_wall_key() -> None:
    from duckclaw.graphs.on_the_fly_commands import chat_id_from_goals_cron_wall_key

    assert chat_id_from_goals_cron_wall_key("chat_99_goals_cron_wall") == "99"


def test_execute_goals_rm_wall_clears_spec(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import (
        _GOALS_CRON_WALL_KEY,
        execute_goals,
        get_chat_state,
    )

    db_path = str(tmp_path / "rmw.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    wall_json = '{"v":1,"tz":"America/Bogota","kind":"every","every_h":9,"every_mi":0,"weekdays":[]}'
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_33_worker_id", "manager", "chat_33_goals", "[]"],
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?)",
        ["chat_33_goals_cron_wall", wall_json],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 33, "--rm wall", tenant_id="default")
    assert "eliminado" in (out or "").lower()
    with DuckClaw(db_path, read_only=True) as db:
        assert not (get_chat_state(db, 33, _GOALS_CRON_WALL_KEY) or "").strip()


def test_execute_goals_rm_delta_aliases_and_noop(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import (
        _GOALS_DELTA_SECONDS_KEY,
        execute_goals,
        get_chat_state,
    )

    db_path = str(tmp_path / "rmd.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_44_worker_id", "manager", "chat_44_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        assert "intervalo activa" in execute_goals(db, 44, "--rm interval", tenant_id="default")
        execute_goals(db, 44, "--delta 2min", tenant_id="default")
        out_rm = execute_goals(db, 44, "--rm interval", tenant_id="default")
    assert "eliminada" in (out_rm or "").lower() or "eliminado" in (out_rm or "").lower()
    with DuckClaw(db_path, read_only=True) as db:
        assert (get_chat_state(db, 44, _GOALS_DELTA_SECONDS_KEY) or "0").strip() == "0"


def test_execute_goals_rm_unknown_id(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import execute_goals

    db_path = str(tmp_path / "rmu.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_1_worker_id", "manager", "chat_1_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 1, "--rm foobar", tenant_id="default")
    assert "desconocido" in (out or "").lower()
