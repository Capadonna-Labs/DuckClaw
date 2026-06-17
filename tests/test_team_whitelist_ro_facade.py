"""Regresión: /team --add debe persistir cuando get_db() es GatewayDbEphemeralReadonly (API Gateway)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from duckclaw import DuckClaw
from duckclaw.gateway_db import GatewayDbEphemeralReadonly
from duckclaw.graphs import graph_server
from duckclaw.graphs.on_the_fly_commands import handle_command


def test_team_add_persists_with_ro_get_db_facade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, owner_user_id: str
) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)
    path = str(tmp_path / "db" / "private" / owner_user_id / "gw_ro_facade.duckdb")
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", path)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", owner_user_id)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fly = DuckClaw(path, read_only=False)
    monkeypatch.setattr(graph_server, "get_db", lambda: GatewayDbEphemeralReadonly(path))

    reply = handle_command(
        fly,
        "chat_ro",
        "/team --add 999 other admin",
        requester_id=owner_user_id,
        tenant_id="Orchestrator",
    )
    assert reply and "Añadido" in reply

    raw = fly.query(
        "SELECT user_id, role FROM main.authorized_users "
        "WHERE lower(tenant_id)=lower('Orchestrator') AND user_id='999' LIMIT 1"
    )
    parsed: Any = json.loads(raw) if isinstance(raw, str) else raw
    assert parsed and str(parsed[0].get("user_id")) == "999"
    fly.close()


def test_team_add_name_before_numeric_telegram_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, owner_user_id: str
) -> None:
    """Orden habitual en Telegram: nombre primero, luego el user_id numérico."""
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)
    path = str(tmp_path / "db" / "private" / owner_user_id / "gw_name_first.duckdb")
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", path)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", owner_user_id)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fly = DuckClaw(path, read_only=False)
    monkeypatch.setattr(graph_server, "get_db", lambda: GatewayDbEphemeralReadonly(path))

    reply = handle_command(
        fly,
        "chat_ro",
        "/team --add Rosas 8320614991 user",
        requester_id=owner_user_id,
        tenant_id="Orchestrator",
    )
    assert reply and "Añadido" in reply

    raw = fly.query(
        "SELECT user_id, username FROM main.authorized_users "
        "WHERE lower(tenant_id)=lower('Orchestrator') AND user_id='8320614991' LIMIT 1"
    )
    parsed: Any = json.loads(raw) if isinstance(raw, str) else raw
    assert parsed and str(parsed[0].get("user_id")) == "8320614991"
    assert "Rosas" in str(parsed[0].get("username") or "")
    fly.close()
