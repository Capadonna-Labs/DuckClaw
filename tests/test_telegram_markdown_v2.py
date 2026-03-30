"""Escape MarkdownV2 para webhooks n8n → Telegram."""

from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2


def test_escape_period_for_markdown_v2() -> None:
    assert escape_telegram_markdown_v2("Listo, preparando respuesta.") == r"Listo, preparando respuesta\."


def test_escape_preserves_tg_user_link() -> None:
    raw = "[Juan](tg://user?id=1726618406) listo."
    assert escape_telegram_markdown_v2(raw) == "[Juan](tg://user?id=1726618406) listo\\."


def test_empty_string() -> None:
    assert escape_telegram_markdown_v2("") == ""
