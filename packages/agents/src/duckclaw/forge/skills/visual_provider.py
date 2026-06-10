"""Resolucion de proveedor visual por chat (ComfyUI local vs Fal.ai cloud)."""

from __future__ import annotations

import os
from typing import Any, Literal

VisualProvider = Literal["local", "fal"]

_CHAT_STATE_KEY = "comfyui_provider"


def _comfy_available() -> bool:
    url = (os.environ.get("COMFYUI_API_URL") or "").strip()
    return bool(url)


def _fal_available() -> bool:
    from duckclaw.fal_env import fal_api_key_configured

    return fal_api_key_configured()


def default_visual_provider() -> VisualProvider:
    if _comfy_available():
        return "local"
    if _fal_available():
        return "fal"
    return "local"


def resolve_visual_provider(db: Any, chat_id: Any) -> VisualProvider:
    """Lee agent_config por chat; fallback segun env disponible."""
    raw = ""
    if db is not None and chat_id is not None:
        try:
            from duckclaw.graphs.on_the_fly_commands import get_chat_state

            raw = (get_chat_state(db, chat_id, _CHAT_STATE_KEY) or "").strip().lower()
        except Exception:
            raw = ""
    if raw in ("local", "fal"):
        if raw == "fal" and not _fal_available():
            return default_visual_provider()
        if raw == "local" and not _comfy_available():
            if _fal_available():
                return "fal"
            return "local"
        return raw  # type: ignore[return-value]
    return default_visual_provider()


def provider_status_message(provider: VisualProvider) -> str:
    local_ok = _comfy_available()
    fal_ok = _fal_available()
    lines = [
        f"Proveedor activo: {provider}",
        f"  local (ComfyUI): {'disponible' if local_ok else 'no configurado (COMFYUI_API_URL)'}",
        f"  fal (Fal.ai): {'disponible' if fal_ok else 'no configurado (FAL_KEY)'}",
    ]
    return "\n".join(lines)