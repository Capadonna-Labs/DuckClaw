"""
Secretos solo en .env (raíz del repo). No persistir en ecosystem PM2 ni api_gateways_pm2.json.
"""

from __future__ import annotations

import re

# Claves que nunca deben escribirse en config/ecosystem.api.config.cjs ni api_gateways_pm2.json.
SECRET_ENV_KEYS: frozenset[str] = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "TAVILY_API_KEY",
        "LANGCHAIN_API_KEY",
        "GITHUB_TOKEN",
        "N8N_AUTH_KEY",
        "IBKR_PORTFOLIO_API_KEY",
        "DUCKCLAW_TAILSCALE_AUTH_KEY",
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_BOT_TOKEN",
        # Rutas compactas incluyen bot_token en el valor.
        "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES",
    }
)

_SECRET_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_AUTH_KEY")

# Al arrancar el gateway, .env gana sobre env heredado de PM2 para estas claves.
DOTENV_OVERRIDE_KEYS: frozenset[str] = frozenset(
    SECRET_ENV_KEYS
    | {
        "DUCKCLAW_LLM_PROVIDER",
        "DUCKCLAW_LLM_MODEL",
        "DUCKCLAW_LLM_BASE_URL",
    }
)


def is_secret_env_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return False
    if k in SECRET_ENV_KEYS:
        return True
    ku = k.upper()
    if ku.startswith("TELEGRAM_") and (
        ku.endswith("_TOKEN") or ku == "TELEGRAM_BOT_TOKEN" or "WEBHOOK" in ku
    ):
        return True
    return any(ku.endswith(suf) for suf in _SECRET_SUFFIXES)


def strip_secrets_from_env(env: dict[str, str]) -> dict[str, str]:
    """Devuelve copia sin claves secretas (para JSON/PM2 persistido)."""
    return {k: v for k, v in env.items() if not is_secret_env_key(k)}


def apply_dotenv_overrides_to_os_environ(flat: dict[str, str]) -> None:
    """Aplica claves de .env que deben sustituir valores heredados de PM2."""
    import os

    for key in DOTENV_OVERRIDE_KEYS:
        val = (flat.get(key) or "").strip()
        if val:
            os.environ[key] = val
