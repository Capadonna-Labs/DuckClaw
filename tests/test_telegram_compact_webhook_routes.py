"""Parsing y resolución de rutas Telegram compactas (path multiplex, solo .env)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_API_GW = REPO_ROOT / "services" / "api-gateway"
if str(_API_GW) not in sys.path:
    sys.path.insert(0, str(_API_GW))

from core.telegram_compact_webhook_routes import (
    compact_route_to_path_binding,
    fastapi_relative_path,
    parse_compact_telegram_webhook_routes,
)
from duckclaw.integrations.telegram.compact_webhook_routes import (
    TelegramCompactWebhookRoute,
    serialize_compact_telegram_webhook_routes,
)


def test_serialize_compact_roundtrip() -> None:
    routes = [
        TelegramCompactWebhookRoute(
            bot_name="mybot",
            bot_token="8266213716:AAG5xx",
            webhook_path="/api/v1/telegram/mybot",
            worker_id="Worker-A",
            tenant_id="TenantA",
            vault_env_var="DUCKCLAW_MY_VAULT_DB_PATH",
        ),
    ]
    raw = serialize_compact_telegram_webhook_routes(routes)
    again = parse_compact_telegram_webhook_routes(raw)
    assert len(again) == 1
    assert again[0].bot_name == "mybot"
    assert again[0].worker_id == "Worker-A"
    assert again[0].tenant_id == "TenantA"


def test_parse_compact_extended_format() -> None:
    raw = (
        "bot_a:tok_a:/api/v1/telegram/bot_a:Worker-A:TenantA,"
        "bot_b:tok_b:/api/v1/telegram/bot_b:Worker-B:TenantB:DUCKCLAW_OTHER_DB_PATH"
    )
    routes = parse_compact_telegram_webhook_routes(raw)
    assert len(routes) == 2
    assert routes[0].worker_id == "Worker-A"
    assert routes[1].vault_env_var == "DUCKCLAW_OTHER_DB_PATH"


def test_parse_rejects_missing_worker_tenant() -> None:
    raw = "mybot:tok:/api/v1/telegram/mybot"
    with pytest.raises(ValueError, match="Formato inválido"):
        parse_compact_telegram_webhook_routes(raw)


def test_parse_rejects_duplicate_path() -> None:
    raw = (
        "a:1:/api/v1/telegram/x:W1:T1,"
        "b:2:/api/v1/telegram/x:W2:T2"
    )
    with pytest.raises(ValueError, match="duplicate webhook_path"):
        parse_compact_telegram_webhook_routes(raw)


def test_fastapi_relative_path() -> None:
    assert fastapi_relative_path("/api/v1/telegram/mybot") == "/mybot"


def test_compact_json_mode_returns_empty() -> None:
    assert parse_compact_telegram_webhook_routes('  [{"secret":"x"}]  ') == []


def test_compact_route_to_binding_resolves_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    repo = tmp_path / "r"
    db = repo / "db" / "f.duckdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_MY_VAULT_DB_PATH", "db/f.duckdb")
    r = parse_compact_telegram_webhook_routes(
        "mybot:t1:/api/v1/telegram/mybot:Worker-A:TenantA:DUCKCLAW_MY_VAULT_DB_PATH"
    )[0]
    b = compact_route_to_path_binding(r)
    assert b.worker_id == "Worker-A"
    assert b.tenant_id == "TenantA"
    assert b.forced_vault_db_path == str(db.resolve())
