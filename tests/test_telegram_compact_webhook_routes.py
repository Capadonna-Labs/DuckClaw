"""Parsing y resolución de rutas Telegram compactas (path multiplex)."""

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


def test_parse_compact_roundtrip() -> None:
    raw = (
        "finanz:8266213716:AAG5xx:/api/v1/telegram/finanz,"
        "siata:8524448524:BB_yy:/api/v1/telegram/siata"
    )
    routes = parse_compact_telegram_webhook_routes(raw)
    assert len(routes) == 2
    assert routes[0].bot_name == "finanz"
    assert routes[0].bot_token == "8266213716:AAG5xx"
    assert routes[0].webhook_path == "/api/v1/telegram/finanz"
    assert routes[1].bot_name == "siata"
    assert routes[1].bot_token == "8524448524:BB_yy"


def test_parse_rejects_duplicate_path() -> None:
    raw = (
        "finanz:8266213716:AAG5xx:/api/v1/telegram/x,"
        "siata:8524448524:BB_yy:/api/v1/telegram/x"
    )
    with pytest.raises(ValueError, match="duplicate webhook_path"):
        parse_compact_telegram_webhook_routes(raw)


def test_fastapi_relative_path() -> None:
    assert fastapi_relative_path("/api/v1/telegram/finanz") == "/finanz"
    assert fastapi_relative_path("/api/v1/telegram/siata/") == "/siata"


def test_compact_json_mode_returns_empty() -> None:
    assert parse_compact_telegram_webhook_routes('  [{"secret":"x"}]  ') == []


def test_compact_route_to_binding_resolves_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    repo = tmp_path / "r"
    db = repo / "db" / "f.duckdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", "db/f.duckdb")
    r = parse_compact_telegram_webhook_routes(
        f"finanz:t1:tok:/api/v1/telegram/finanz"
    )[0]
    b = compact_route_to_path_binding(r)
    assert b.worker_id == "finanz"
    assert b.tenant_id == "Finanzas"
    assert b.forced_vault_db_path == str(db.resolve())


def test_compact_quanttrader_prefers_quant_trader_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    repo = tmp_path / "r"
    qdb = repo / "db" / "private" / "u" / "quant_traderdb1.duckdb"
    fdb = repo / "db" / "private" / "u" / "finanzdb1.duckdb"
    qdb.parent.mkdir(parents=True, exist_ok=True)
    qdb.write_bytes(b"q")
    fdb.write_bytes(b"f")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_QUANT_TRADER_DB_PATH", "db/private/u/quant_traderdb1.duckdb")
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", "db/private/u/finanzdb1.duckdb")
    r = parse_compact_telegram_webhook_routes(
        "quanttrader:t1:tok:/api/v1/telegram/quanttrader"
    )[0]
    b = compact_route_to_path_binding(r)
    assert b.worker_id == "quant_trader"
    assert b.forced_vault_db_path == str(qdb.resolve())
