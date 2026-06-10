"""Resolucion zero-trust de API key Fal.ai desde variables de entorno."""

from __future__ import annotations

import os

_FAL_KEY_CANDIDATES = ("FAL_KEY", "FAL_API_KEY")


def resolve_fal_api_key(token_env: str | None = None) -> str:
    """
    Devuelve la API key Fal sin loguearla.

    Prioridad:
    1. token_env del manifest (p. ej. FAL_KEY)
    2. FAL_KEY
    3. FAL_API_KEY (alias comun en .env)
    """
    if (token_env or "").strip():
        val = (os.environ.get(token_env.strip()) or "").strip()
        if val:
            return val
    for key in _FAL_KEY_CANDIDATES:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def fal_api_key_configured(token_env: str | None = None) -> bool:
    return bool(resolve_fal_api_key(token_env))