# packages/shared/src/duckclaw/integrations/telegram/telegram_webhook_secret_header.py
"""Validación del secreto opcional del webhook de Telegram Bot API."""

from __future__ import annotations

import os

# Cabecera documentada por Telegram para webhooks con secret_token en setWebhook.
TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def telegram_webhook_secret_expected_from_env() -> str:
    """Valor esperado (vacío = no se exige cabecera)."""
    return (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()


def is_valid_telegram_webhook_secret_token(header_value: str | None) -> bool:
    """
    True si la cabecera coincide con TELEGRAM_WEBHOOK_SECRET,
    o si el secreto no está configurado (solo para desarrollo local).
    """
    expected = telegram_webhook_secret_expected_from_env()
    if not expected:
        return True
    got = (header_value or "").strip()
    return bool(got) and got == expected
