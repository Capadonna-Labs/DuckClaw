"""Canales agnósticos — rutas y URN."""

from __future__ import annotations

from duckclaw.channels import (
    GatewayDeliveryContext,
    build_discord_session_id,
    build_telegram_session_id,
    load_channel_route_bindings,
    urn_sessions_enabled,
)


def test_gateway_delivery_context_legacy_telegram() -> None:
    dc = GatewayDeliveryContext.from_legacy_telegram(
        telegram_multipart_tail_delivery="native",
        telegram_mcp=None,
        telegram_forced_vault_db_path=None,
        outbound_telegram_bot_token="abc",
    )
    assert dc.channel == "telegram"
    assert dc.outbound_bot_token == "abc"
    assert dc.telegram_multipart_tail_delivery == "native"


def test_telegram_session_id_without_urn(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CHANNEL_URN_SESSIONS", raising=False)
    assert build_telegram_session_id("12345") == "12345"


def test_telegram_session_id_with_urn(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CHANNEL_URN_SESSIONS", "1")
    assert build_telegram_session_id("12345") == "telegram:12345"


def test_discord_session_id_shape() -> None:
    s = build_discord_session_id("g", "c", "u")
    assert s == "discord:g:c:u"


def test_load_channel_routes_empty(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CHANNEL_ROUTES", raising=False)
    assert load_channel_route_bindings() == []


def test_urn_sessions_enabled(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CHANNEL_URN_SESSIONS", raising=False)
    assert urn_sessions_enabled() is False
    monkeypatch.setenv("DUCKCLAW_CHANNEL_URN_SESSIONS", "1")
    assert urn_sessions_enabled() is True
