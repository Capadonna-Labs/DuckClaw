from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from duckclaw.graphs.on_the_fly_commands import (
    build_goals_proactive_system_event_message,
    chat_id_from_goals_delta_config_key,
    clear_goals_proactive_schedule,
    execute_goals,
    format_goals_countdown_human,
    format_goals_delta_interval_human,
    get_chat_state,
    parse_goals_delta_arg,
)
from duckclaw.graphs.proactive_review_markers import (
    GOALS_PROACTIVE_REVIEW_PHRASE_CRONS,
    GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY,
    proactive_review_event_phrase_in_text,
)
import services.heartbeat.main as heartbeat


def _patch_heartbeat_sync_duckdb_write(monkeypatch: Any) -> None:
    """enqueue_duckdb_write_sync solo encola Redis; sin db-writer el .duckdb no cambia en tests."""

    import duckdb

    def _sync(
        *,
        db_path: str,
        query: str,
        params: list[Any] | None = None,
        **kwargs: Any,
    ) -> str:
        con = duckdb.connect(db_path)
        try:
            con.execute(query, list(params or []))
        finally:
            con.close()
        return "test-task"

    monkeypatch.setattr(heartbeat, "enqueue_duckdb_write_sync", _sync)


def test_parse_goals_delta_arg_off() -> None:
    assert parse_goals_delta_arg("off") == (0, None)
    assert parse_goals_delta_arg("0") == (0, None)


def test_parse_goals_delta_arg_units() -> None:
    assert parse_goals_delta_arg("90s") == (90, None)
    secs, err = parse_goals_delta_arg("20min")
    assert err is None and secs == 20 * 60
    secs2, err2 = parse_goals_delta_arg("2h")
    assert err2 is None and secs2 == 2 * 3600


def test_parse_goals_delta_arg_min_clamp() -> None:
    secs, err = parse_goals_delta_arg("30s")
    assert secs is None and err is not None


def test_chat_id_from_goals_delta_config_key() -> None:
    assert chat_id_from_goals_delta_config_key("chat_1726618406_goals_delta_seconds") == "1726618406"
    assert chat_id_from_goals_delta_config_key("chat_foo_bar_goals_delta_seconds") == "foo_bar"
    assert chat_id_from_goals_delta_config_key("wrong") is None


def test_format_goals_delta_interval_human() -> None:
    assert "60" in format_goals_delta_interval_human(60) or "min" in format_goals_delta_interval_human(60)
    assert format_goals_delta_interval_human(3600) == "1h"


def test_format_goals_countdown_human() -> None:
    assert format_goals_countdown_human(0) == "menos de 1 s"
    assert "45" in format_goals_countdown_human(45)
    assert "min" in format_goals_countdown_human(125)


def test_build_goals_proactive_system_event_includes_overnight_mission() -> None:
    msg = build_goals_proactive_system_event_message(
        [{"belief_key": "overnight_squeeze", "title": "Overnight Gap Squeeze (cierre + gap)"}],
        trading_session_objective="overnight_gap_squeeze",
    )
    assert "[SYSTEM_EVENT:" in msg
    assert "MISIÓN: OVERNIGHT GAP SQUEEZE" in msg
    assert GOALS_PROACTIVE_REVIEW_PHRASE_CRONS in msg
    assert GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY not in msg
    legacy = msg.replace(GOALS_PROACTIVE_REVIEW_PHRASE_CRONS, GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY)
    assert proactive_review_event_phrase_in_text(msg)
    assert proactive_review_event_phrase_in_text(legacy)


def test_run_goals_proactive_tick_posts_system_event(tmp_path: Path, monkeypatch: Any) -> None:
    import duckdb

    db_path = str(tmp_path / "gw.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_99_goals_delta_seconds",
            "1",
            "chat_99_goals",
            json.dumps([{"belief_key": "k", "title": "Test goal"}]),
            "chat_99_worker_id",
            "Quant-Trader",
            "chat_99_goals_proactive_tenant_id",
            "Cuantitativo",
            "chat_99_goals_proactive_last_fire_epoch",
            "",
        ],
    )
    con.close()

    posts: list[dict[str, Any]] = []

    class Resp:
        status_code = 200
        text = "ok"

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Resp:
            posts.append({"args": a, "kwargs": kw})
            return Resp()

    monkeypatch.setenv("DUCKCLAW_GOALS_TICKER_DB_PATH", db_path)
    _patch_heartbeat_sync_duckdb_write(monkeypatch)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
    kw = posts[0]["kwargs"]
    assert kw["json"]["is_system_prompt"] is True
    assert kw["json"]["skip_session_lock"] is True
    assert kw["json"]["tenant_id"] == "Cuantitativo"
    assert "SYSTEM_EVENT" in kw["json"]["message"]
    url = posts[0]["args"][0]
    assert "Quant-Trader" in url
    assert "/chat" in url
    assert posts[0]["kwargs"]["json"].get("vault_db_path") in (None, db_path)

    con2 = duckdb.connect(db_path, read_only=True)
    row = con2.execute(
        "SELECT value FROM agent_config WHERE key = 'chat_99_goals_proactive_last_fire_epoch'"
    ).fetchone()
    con2.close()
    assert row and float(row[0]) > 0


def test_run_goals_proactive_skips_manager_worker(tmp_path: Path, monkeypatch: Any) -> None:
    import duckdb

    db_path = str(tmp_path / "gw2.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_1_goals_delta_seconds",
            "60",
            "chat_1_goals",
            json.dumps([{"belief_key": "k", "title": "G"}]),
            "chat_1_worker_id",
            "manager",
            "chat_1_goals_proactive_tenant_id",
            "default",
        ],
    )
    con.close()

    posted: list[Any] = []

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Any:
            posted.append(1)
            raise AssertionError("should not post")

    monkeypatch.setenv("DUCKCLAW_GOALS_TICKER_DB_PATH", db_path)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())
    assert posted == []


def test_run_goals_proactive_finds_delta_in_sibling_vault_duckdb(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Fly /crons escribe en la bóveda (p. ej. quant_traderdb1.duckdb); el ticker debe verla aunque el hub sea otro .duckdb."""
    import duckdb

    priv = tmp_path / "private" / "u1"
    priv.mkdir(parents=True)
    hub = str(priv / "finanzdb1.duckdb")
    vault = str(priv / "quant_traderdb1.duckdb")

    con = duckdb.connect(hub)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.close()

    con = duckdb.connect(vault)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_77_goals_delta_seconds",
            "1",
            "chat_77_goals",
            json.dumps([{"belief_key": "k", "title": "Vault goal"}]),
            "chat_77_worker_id",
            "Quant-Trader",
            "chat_77_goals_proactive_tenant_id",
            "Cuantitativo",
            "chat_77_goals_proactive_last_fire_epoch",
            "",
        ],
    )
    con.close()

    posts: list[dict[str, Any]] = []

    class Resp:
        status_code = 200
        text = "ok"

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Resp:
            posts.append({"args": a, "kwargs": kw})
            return Resp()

    monkeypatch.delenv("DUCKCLAW_GOALS_TICKER_DB_PATH", raising=False)
    monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: hub)
    _patch_heartbeat_sync_duckdb_write(monkeypatch)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
    vault_resolved = str(Path(vault).resolve())
    assert posts[0]["kwargs"]["json"].get("vault_db_path") == vault_resolved
    con2 = duckdb.connect(vault, read_only=True)
    row = con2.execute(
        "SELECT value FROM agent_config WHERE key = 'chat_77_goals_proactive_last_fire_epoch'"
    ).fetchone()
    con2.close()
    assert row and float(row[0]) > 0


def test_run_goals_proactive_cuantitativo_tenant_defaults_quant_worker(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Multiplex: worker_id en bóveda puede quedar en manager; tenant Cuantitativo enruta a Quant-Trader."""
    import duckdb

    db_path = str(tmp_path / "vaultq.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_5_goals_delta_seconds",
            "1",
            "chat_5_goals",
            json.dumps([{"belief_key": "k", "title": "G"}]),
            "chat_5_worker_id",
            "manager",
            "chat_5_goals_proactive_tenant_id",
            "Cuantitativo",
            "chat_5_goals_proactive_last_fire_epoch",
            "",
        ],
    )
    con.close()

    posts: list[dict[str, Any]] = []

    class Resp:
        status_code = 200
        text = "ok"

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Resp:
            posts.append({"args": a, "kwargs": kw})
            return Resp()

    monkeypatch.setenv("DUCKCLAW_GOALS_TICKER_DB_PATH", db_path)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
    assert "Quant-Trader" in posts[0]["args"][0]


def test_run_goals_proactive_trading_session_event_payload(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import duckdb

    db_path = str(tmp_path / "vault_trading_tick.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE SCHEMA IF NOT EXISTS quant_core;
        CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
          id VARCHAR PRIMARY KEY,
          mode VARCHAR NOT NULL,
          tickers VARCHAR NOT NULL DEFAULT '',
          session_uid VARCHAR,
          session_goal JSON,
          status VARCHAR NOT NULL DEFAULT 'ACTIVE',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO quant_core.trading_sessions (id, mode, tickers, session_uid, session_goal, status) VALUES (?, ?, ?, ?, CAST(? AS JSON), ?)",
        [
            "active",
            "paper",
            "NVDA,SPY",
            "uid-123",
            json.dumps({"signal_threshold": "GAS"}),
            "ACTIVE",
        ],
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_88_goals_delta_seconds",
            "1",
            "chat_88_goals",
            json.dumps([{"belief_key": "k", "title": "session goal"}]),
            "chat_88_worker_id",
            "Quant-Trader",
            "chat_88_goals_proactive_tenant_id",
            "Cuantitativo",
            "chat_88_goals_proactive_last_fire_epoch",
            "",
            "chat_88_goals_delta_meta",
            json.dumps({"trigger": "trading_session", "session_uid": "uid-123"}),
        ],
    )
    con.close()

    posts: list[dict[str, Any]] = []

    class Resp:
        status_code = 200
        text = "ok"

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Resp:
            posts.append({"args": a, "kwargs": kw})
            return Resp()

    monkeypatch.setenv("DUCKCLAW_GOALS_TICKER_DB_PATH", db_path)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
    msg = posts[0]["kwargs"]["json"]["message"]
    assert "TRADING_TICK" in msg
    assert "uid-123" in msg


def test_run_goals_proactive_trading_session_empty_manager_goals_still_ticks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Sin filas en chat_goals el ticker no debe borrar el delta si trigger=trading_session y worker=Quant."""
    import duckdb

    db_path = str(tmp_path / "vault_trading_tick_empty_goals.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE SCHEMA IF NOT EXISTS quant_core;
        CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
          id VARCHAR PRIMARY KEY,
          mode VARCHAR NOT NULL,
          tickers VARCHAR NOT NULL DEFAULT '',
          session_uid VARCHAR,
          session_goal JSON,
          status VARCHAR NOT NULL DEFAULT 'ACTIVE',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO quant_core.trading_sessions (id, mode, tickers, session_uid, session_goal, status) VALUES (?, ?, ?, ?, CAST(? AS JSON), ?)",
        [
            "active",
            "paper",
            "NVDA,SPY",
            "uid-999",
            json.dumps({"signal_threshold": "GAS"}),
            "ACTIVE",
        ],
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_77_goals_delta_seconds",
            "1",
            "chat_77_goals",
            json.dumps([]),
            "chat_77_worker_id",
            "Quant-Trader",
            "chat_77_goals_proactive_tenant_id",
            "Cuantitativo",
            "chat_77_goals_proactive_last_fire_epoch",
            "",
            "chat_77_goals_delta_meta",
            json.dumps({"trigger": "trading_session", "session_uid": "uid-999"}),
        ],
    )
    con.close()

    posts: list[dict[str, Any]] = []

    class Resp:
        status_code = 200
        text = "ok"

    class DummyClient:
        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Resp:
            posts.append({"args": a, "kwargs": kw})
            return Resp()

    monkeypatch.setenv("DUCKCLAW_GOALS_TICKER_DB_PATH", db_path)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
    msg = posts[0]["kwargs"]["json"]["message"]
    assert "TRADING_TICK" in msg
    assert "uid-999" in msg

    con2 = duckdb.connect(db_path)
    row = con2.execute(
        "SELECT value FROM agent_config WHERE key = 'chat_77_goals_delta_seconds'"
    ).fetchone()
    con2.close()
    assert row is not None and str(row[0]).strip() == "1"


def test_execute_goals_delta_cli_forces_goals_cli_meta_and_cooldown_now(
    tmp_path: Path,
) -> None:
    """Explicit `/crons --delta` must not inherit trading_session meta (avoids full TRADING_TICK on poll)."""
    import duckdb

    from duckclaw import DuckClaw

    db_path = str(tmp_path / "execute_goals_cli_meta.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE SCHEMA IF NOT EXISTS quant_core;
        CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
          id VARCHAR PRIMARY KEY,
          mode VARCHAR NOT NULL,
          tickers VARCHAR NOT NULL DEFAULT '',
          session_uid VARCHAR,
          session_goal JSON,
          status VARCHAR NOT NULL DEFAULT 'ACTIVE',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO quant_core.trading_sessions (id, mode, tickers, session_uid, session_goal, status) VALUES (?, ?, ?, ?, CAST(? AS JSON), ?)",
        [
            "active",
            "paper",
            "SPY",
            "uid-abc",
            json.dumps({"objective": "overnight_gap_squeeze", "signal_threshold": "GAS"}),
            "ACTIVE",
        ],
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_51_worker_id",
            "Quant-Trader",
            "chat_51_goals",
            json.dumps([{"belief_key": "k", "title": "G"}]),
            "chat_51_goals_delta_meta",
            json.dumps({"trigger": "trading_session", "session_uid": "uid-abc"}),
            "chat_51_goals_proactive_last_fire_epoch",
            "",
        ],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 51, "--delta 1h", tenant_id="Cuantitativo")
    assert "Revisión proactiva" in (out or "")

    with DuckClaw(db_path, read_only=True) as db:
        meta_raw = (get_chat_state(db, 51, "goals_delta_meta") or "").strip()
        em = json.loads(meta_raw) if meta_raw else {}
        assert em.get("trigger") == "goals_cli"
        last = (get_chat_state(db, 51, "goals_proactive_last_fire_epoch") or "").strip()
    assert last and float(last) > 0


def test_clear_goals_delta_off_clears_schedule_on_hub_and_sibling_vault(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """/crons --delta off debe poner goals_delta_seconds=0 en hub y bóveda; si no, el ticker sigue en bucle."""
    import duckdb

    from duckclaw import DuckClaw

    priv = tmp_path / "private" / "u1"
    priv.mkdir(parents=True)
    hub = str(priv / "finanzdb1.duckdb")
    vault = str(priv / "quant_traderdb1.duckdb")

    def _bootstrap(p: str) -> None:
        c = duckdb.connect(p)
        c.execute(
            "CREATE TABLE agent_config (key VARCHAR PRIMARY KEY, value TEXT, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        c.close()

    _bootstrap(hub)
    _bootstrap(vault)

    def _seed(p: str) -> None:
        c = duckdb.connect(p)
        c.executemany(
            "INSERT INTO agent_config (key, value) VALUES (?, ?)",
            [
                ("chat_42_goals_delta_seconds", "120"),
                ("chat_42_goals_proactive_tenant_id", "Cuantitativo"),
            ],
        )
        c.close()

    _seed(hub)
    _seed(vault)

    monkeypatch.delenv("DUCKCLAW_GOALS_TICKER_DB_PATH", raising=False)
    monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: hub)

    with DuckClaw(vault, read_only=False, engine="python") as dbv:
        clear_goals_proactive_schedule(dbv, 42)

    for p in (hub, vault):
        con = duckdb.connect(p, read_only=True)
        row = con.execute(
            "SELECT value FROM agent_config WHERE key = 'chat_42_goals_delta_seconds' LIMIT 1"
        ).fetchone()
        con.close()
        assert row is not None and int(str(row[0]).strip() or "0") == 0


def test_iter_goals_delta_clear_paths_scoped_excludes_other_private_vaults(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """``off`` no debe enumerar DuckDB de otros ``db/private/<uid>`` (reduce bloqueos)."""
    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    root = tmp_path / "db" / "private"
    u_a = root / "111"
    u_b = root / "222"
    u_a.mkdir(parents=True)
    u_b.mkdir(parents=True)
    hub_a = u_a / "finanzdb1.duckdb"
    quant_a = u_a / "quant_traderdb1.duckdb"
    other_b = u_b / "finanzdb1.duckdb"
    hub_a.touch()
    quant_a.touch()
    other_b.touch()

    monkeypatch.delenv("DUCKCLAW_GOALS_TICKER_DB_PATH", raising=False)
    monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: str(hub_a))

    paths = {str(Path(p).resolve()) for p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=str(quant_a))}
    assert str(hub_a.resolve()) in paths
    assert str(quant_a.resolve()) in paths
    assert str(other_b.resolve()) not in paths


def test_dispatch_crons_and_goals_alias_same_handler(tmp_path: Path) -> None:
    """`/_dispatch_fly_command` trata `crons` y `goals` como el mismo handler (execute_goals)."""
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import _dispatch_fly_command

    db_path = str(tmp_path / "dispatch_crons_alias.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_11_worker_id", "manager", "chat_11_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out_crons = _dispatch_fly_command(db, 11, "crons", "", tenant_id="default")
        out_goals = _dispatch_fly_command(db, 11, "goals", "", tenant_id="default")
    assert out_crons == out_goals
    assert out_crons is not None
    assert "/crons" in (out_crons or "")


def test_crons_list_includes_user_and_platform_blocks(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw

    db_path = str(tmp_path / "crons_list_platform.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_7_worker_id", "manager", "chat_7_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 7, "")
    assert "Tus crons" in (out or "")
    assert "Del bot (infraestructura)" in (out or "")
    assert "45" in (out or "") and "3600" in (out or "")
    assert "/crons --reset" in (out or "")


def test_crons_list_platform_summary_respects_env(tmp_path: Path, monkeypatch: Any) -> None:
    import duckdb

    from duckclaw import DuckClaw

    monkeypatch.setenv("GOALS_TICKER_POLL_SECONDS", "120")
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "7200")
    monkeypatch.setenv("DUCKCLAW_EMBED_GOALS_TICKER", "false")

    db_path = str(tmp_path / "crons_list_env.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?)",
        ["chat_8_worker_id", "manager", "chat_8_goals", "[]"],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 8, "")
    assert "120" in (out or "")
    assert "7200" in (out or "")
    assert "API Gateway puede ejecutar" not in (out or "")


def test_crons_list_trading_session_meta_note(tmp_path: Path) -> None:
    import duckdb

    from duckclaw import DuckClaw

    db_path = str(tmp_path / "crons_list_session_meta.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    meta = json.dumps({"trigger": "trading_session", "session_uid": "uid-test-1"}, ensure_ascii=False)
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?)",
        ["chat_9_worker_id", "Quant-Trader", "chat_9_goals", "[]", "chat_9_goals_delta_meta", meta],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out = execute_goals(db, 9, "")
    assert "Revisión proactiva (TRADING_TICK)" in (out or "")
    assert "goals_delta_seconds=0" in (out or "")
    assert "session_uid=uid-test-1" in (out or "")
    assert "schedule_quant_trading_proactive_ticks" in (out or "")
    assert "/trading-session" in (out or "")


def test_crons_list_trading_session_meta_with_delta_300(tmp_path: Path) -> None:
    """Listado /crons con intervalo 5 min + meta trading_session: intervalo, cron-id delta y UID."""
    import duckdb

    from duckclaw import DuckClaw

    db_path = str(tmp_path / "crons_list_session_delta300.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    meta = json.dumps(
        {"trigger": "trading_session", "session_uid": "qt-sess-a1"},
        ensure_ascii=False,
    )
    long_uid = "11111111-2222-3333-4444-555555555555"
    meta_long = json.dumps({"trigger": "trading_session", "session_uid": long_uid}, ensure_ascii=False)
    con.execute(
        "INSERT INTO agent_config (key, value) VALUES (?, ?), (?, ?), (?, ?), (?, ?), "
        "(?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "chat_12_worker_id",
            "Quant-Trader",
            "chat_12_goals",
            "[]",
            "chat_12_goals_delta_seconds",
            "300",
            "chat_12_goals_delta_meta",
            meta,
            "chat_13_worker_id",
            "Quant-Trader",
            "chat_13_goals",
            "[]",
            "chat_13_goals_delta_seconds",
            "300",
            "chat_13_goals_delta_meta",
            meta_long,
        ],
    )
    con.close()

    with DuckClaw(db_path, read_only=False) as db:
        out12 = execute_goals(db, 12, "")
        out13 = execute_goals(db, 13, "")
    assert "Revisión proactiva (TRADING_TICK)" in (out12 or "")
    assert "5 min" in (out12 or "")
    assert "cron-id delta" in (out12 or "")
    assert "session_uid=qt-sess-a1" in (out12 or "")
    assert "11111111…" in (out13 or "")
    assert long_uid not in (out13 or "")
