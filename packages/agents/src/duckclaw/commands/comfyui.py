"""DB-first chat commands for visual provider override (/comfyui --provider)."""

from __future__ import annotations

from typing import Any

from duckclaw.commands.chat_state import set_chat_state_via_typed_command
from duckclaw.forge.skills.visual_provider import (
    default_visual_provider,
    provider_status_message,
    resolve_visual_provider,
)

_COMFYUI_PROVIDER_KEY = "comfyui_provider"


def execute_comfyui_provider(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = "default",
) -> str:
    """/comfyui --provider local|fal: motor de generacion visual por chat."""
    raw = (args or "").strip()
    if raw.startswith("--provider"):
        val = raw[len("--provider") :].strip()
    else:
        val = raw
    val = val.strip().lower()
    if val in ("local", "fal"):
        ok, err = set_chat_state_via_typed_command(
            db,
            chat_id,
            _COMFYUI_PROVIDER_KEY,
            val,
            tenant_id=str(tenant_id or "default").strip() or "default",
        )
        if not ok:
            return f"No se pudo actualizar proveedor visual: {err}"
        return (
            f"Proveedor visual establecido en '{val}' para esta sesion.\n"
            + provider_status_message(val)  # type: ignore[arg-type]
        )
    if not val:
        cur = resolve_visual_provider(db, chat_id)
        return (
            "Uso: /comfyui --provider local|fal\n"
            + provider_status_message(cur)
            + f"\nDefault sin override: {default_visual_provider()}"
        )
    return "Uso: /comfyui --provider local|fal"
