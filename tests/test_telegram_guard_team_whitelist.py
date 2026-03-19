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

