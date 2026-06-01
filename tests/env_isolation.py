"""Helpers para aislar pytest del ``.env`` del desarrollador."""

from __future__ import annotations

import pytest

from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS

# Variables que suelen contaminar tests si quedan del .env local.
_MLX_ENV_KEYS: tuple[str, ...] = (
    "MLX_GEMMA4_MODEL_PATH",
    "MLX_MODEL_ID",
    "MLX_MODEL_PATH",
)

_VLM_ENV_KEYS: tuple[str, ...] = (
    "DUCKCLAW_VLM_MLX_BASE_URL",
    "VLM_MLX_BASE_URL",
    "DUCKCLAW_VLM_MLX_PORT",
    "VLM_MLX_PORT",
)

_LLM_PROVIDER_ENV_KEYS: tuple[str, ...] = (
    "DUCKCLAW_LLM_PROVIDER",
    "LLM_PROVIDER",
)

_MISC_ENV_KEYS: tuple[str, ...] = (
    "DUCKCLAW_GATEWAY_TENANT_ID",
    "DUCKCLAW_PM2_PROCESS_NAME",
    "DUCKCLAW_PM2_MATCHED_APP_NAME",
    "DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT",
    "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES",
    "DUCKCLAW_DB_PATH",
)


def clear_gateway_multiplex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quita todas las rutas multiplex del hub (incl. QUANT_TRADER, AXIS, PQRSD)."""
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in _MISC_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def isolate_test_env_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture autouse: cada test empieza sin rutas MLX/DB del .env del host."""
    monkeypatch.setenv("DUCKCLAW_DISABLE_DOTENV", "1")
    clear_gateway_multiplex_env(monkeypatch)
    for key in _MLX_ENV_KEYS + _VLM_ENV_KEYS + _LLM_PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
