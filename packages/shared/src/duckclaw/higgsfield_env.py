"""Resolucion zero-trust de API key Higgsfield desde variables de entorno."""

from __future__ import annotations

import os

_HIGGSFIELD_KEY_CANDIDATES = ("HIGGSFIELD_API_KEY", "HIGGSFIELD_KEY")


def resolve_higgsfield_api_key(token_env: str | None = None) -> str:
    """
    Devuelve la API key Higgsfield sin loguearla.

    Prioridad:
    1. token_env del manifest (p. ej. HIGGSFIELD_API_KEY)
    2. HIGGSFIELD_API_KEY
    3. HIGGSFIELD_KEY (alias)
    """
    if (token_env or "").strip():
        val = (os.environ.get(token_env.strip()) or "").strip()
        if val:
            return val
    for key in _HIGGSFIELD_KEY_CANDIDATES:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def higgsfield_api_key_configured(token_env: str | None = None) -> bool:
    return bool(resolve_higgsfield_api_key(token_env))
