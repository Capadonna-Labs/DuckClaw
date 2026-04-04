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


def test_team_add_persists_with_ro_get_db_facade(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = str(tmp_path / "gw_ro_facade.duckdb")
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", path)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1726618406")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fly = DuckClaw(path, read_only=False)
    monkeypatch.setattr(graph_server, "get_db", lambda: GatewayDbEphemeralReadonly(path))

    reply = handle_command(
        fly,
        "chat_ro",
        "/team --add 999 other admin",
        requester_id="1726618406",
        tenant_id="Finanzas",
    )
    assert reply and "Añadido" in reply

    raw = fly.query(
        "SELECT user_id, role FROM main.authorized_users "
        "WHERE lower(tenant_id)=lower('Finanzas') AND user_id='999' LIMIT 1"
    )
    parsed: Any = json.loads(raw) if isinstance(raw, str) else raw
    assert parsed and str(parsed[0].get("user_id")) == "999"
    fly.close()
