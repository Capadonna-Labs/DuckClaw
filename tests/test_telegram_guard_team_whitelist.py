from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from duckclaw import DuckClaw
from duckclaw.graphs.on_the_fly_commands import handle_command


@pytest.fixture
def db(tmp_path: Path) -> DuckClaw:
    path = str(tmp_path / "gateway_guard_test.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    d = DuckClaw(path)
    # Asegurar tabla whitelist (main schema)
    d.execute(
        """
        CREATE TABLE IF NOT EXISTS main.authorized_users (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            role VARCHAR DEFAULT 'user',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        )
        """
    )
    return d


def test_team_whitelist_list_requires_any_authorized_role(db) -> None:
    # En este test no validamos la pre-autorización del gateway; solo el comando /team.
    d = db
    d.execute(
        """
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES ('default', '123', 'bot_test_user', 'user')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET username=EXCLUDED.username, role=EXCLUDED.role
        """
    )

    reply = handle_command(
        d,
        "chat_1",
        "/team",
        requester_id="123",
        tenant_id="default",
    )
    assert reply is not None
    assert "123" in reply


def test_team_whitelist_add_is_admin_only(db) -> None:
    d = db
    # requester '2' es user (no admin)
    d.execute(
        """
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES ('default', '2', 'user2', 'user')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET username=EXCLUDED.username, role=EXCLUDED.role
        """
    )

    reply = handle_command(
        d,
        "chat_1",
        "/team --add 3 user3",
        requester_id="2",
        tenant_id="default",
    )
    assert reply is not None
    assert "Acceso denegado" in (reply or "")

    rows = d.query(
        "SELECT user_id FROM main.authorized_users WHERE tenant_id='default' AND user_id='3' LIMIT 1"
    )
    # DuckClaw.query devuelve JSON serializado
    import json

    parsed: Any = json.loads(rows) if isinstance(rows, str) else rows
    assert not parsed  # no inserted


def test_team_whitelist_add_admin_allows_insert(db) -> None:
    d = db
    d.execute(
        """
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES ('default', '1', 'admin1', 'admin')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET username=EXCLUDED.username, role=EXCLUDED.role
        """
    )

    reply = handle_command(
        d,
        "chat_1",
        "/team --add 3 user3",
        requester_id="1",
        tenant_id="default",
    )
    assert reply is not None
    assert "Añadido" in reply or "Añadidos" in reply or "Añadido user_id=3" in reply

    rows = d.query(
        "SELECT user_id, role FROM main.authorized_users WHERE tenant_id='default' AND user_id='3' LIMIT 1"
    )
    import json

    parsed: Any = json.loads(rows) if isinstance(rows, str) else rows
    assert parsed and parsed[0]["user_id"] == "3"


def test_register_wr_member_requires_wr_admin(db) -> None:
    d = db
    # bootstrap admin for wr tenant
    d.execute("CREATE SCHEMA IF NOT EXISTS war_room_core")
    d.execute(
        """
        CREATE TABLE IF NOT EXISTS war_room_core.wr_members (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            clearance_level VARCHAR,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        )
        """
    )
    d.execute(
        """
        INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level)
        VALUES ('wr_-1001', '1', 'admin', 'admin')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET clearance_level='admin'
        """
    )

    denied = handle_command(
        d,
        "chat_1",
        "/register_wr_member 77 operator maria",
        requester_id="2",
        tenant_id="wr_-1001",
    )
    assert denied is not None
    assert "Acceso denegado" in denied

    ok = handle_command(
        d,
        "chat_1",
        "/register_wr_member 77 operator maria",
        requester_id="1",
        tenant_id="wr_-1001",
    )
    assert ok is not None
    assert "registrado" in ok.lower()


def test_execute_signal_wr_requires_admin(db, monkeypatch: pytest.MonkeyPatch) -> None:
    d = db
    d.execute("CREATE SCHEMA IF NOT EXISTS war_room_core")
    d.execute(
        """
        CREATE TABLE IF NOT EXISTS war_room_core.wr_members (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            clearance_level VARCHAR,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        )
        """
    )
    d.execute(
        """
        INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level)
        VALUES ('wr_-1001', '1', 'admin', 'admin')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET clearance_level='admin'
        """
    )

    monkeypatch.setattr("duckclaw.graphs.graph_server.get_db", lambda: d)
    monkeypatch.setattr("duckclaw.forge.skills.quant_hitl.grant_execute_order", lambda *_a, **_k: None)
    signal_id = "123e4567-e89b-12d3-a456-426614174000"

    denied = handle_command(
        d,
        "chat_2",
        f"/execute_signal {signal_id}",
        requester_id="2",
        tenant_id="wr_-1001",
    )
    assert denied is not None
    assert "requiere clearance admin" in denied.lower()

    allowed = handle_command(
        d,
        "chat_2",
        f"/execute_signal {signal_id}",
        requester_id="1",
        tenant_id="wr_-1001",
    )
    assert allowed is not None
    assert "confirmación registrada" in allowed.lower()

