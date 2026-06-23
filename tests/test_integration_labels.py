"""Tests for integration channel → human label mapping."""

from __future__ import annotations

from duckclaw.channels.integration_labels import resolve_integration_label


def test_http_admin_conv_maps_to_interfaz() -> None:
    ch, label = resolve_integration_label("http", chat_id="admin-conv-f4123501f9aa488094762fac703a5960")
    assert ch == "http"
    assert label == "Interfaz"


def test_telegram_channel_label() -> None:
    ch, label = resolve_integration_label("telegram", chat_id="123456789")
    assert ch == "telegram"
    assert label == "Telegram"


def test_discord_channel_label() -> None:
    ch, label = resolve_integration_label("discord", chat_id="discord-session-1")
    assert ch == "discord"
    assert label == "Discord"


def test_edge_channel_label() -> None:
    ch, label = resolve_integration_label("edge", chat_id="edge-device-1")
    assert ch == "edge"
    assert label == "Edge Device"
