from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from duckclaw.graphs.on_the_fly_commands import (
    chat_id_from_goals_delta_config_key,
    format_goals_countdown_human,
    format_goals_delta_interval_human,
    parse_goals_delta_arg,
)
import services.heartbeat.main as heartbeat


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
    """Fly /goals escribe en la bóveda (p. ej. quant_traderdb1.duckdb); el ticker debe verla aunque el hub sea otro .duckdb."""
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
    monkeypatch.setattr(heartbeat, "get_gateway_db_path", lambda: hub)
    monkeypatch.setattr(heartbeat, "httpx", type("M", (), {"AsyncClient": staticmethod(lambda: DummyClient())}))

    asyncio.run(heartbeat._run_goals_proactive_tick())

    assert len(posts) == 1
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
