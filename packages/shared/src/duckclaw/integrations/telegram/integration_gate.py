"""Opt-in: Telegram es integración opcional, no dependencia del stack core."""

from __future__ import annotations

import os


def telegram_integration_env_configured() -> bool:
    """True si hay señales mínimas de configuración Telegram en el entorno."""
    if (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip():
        return True
    if (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip():
        return True
    for key, val in os.environ.items():
        if key.startswith("TELEGRAM_") and key.endswith("_TOKEN") and (val or "").strip():
            return True
    return False
