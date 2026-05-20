"""Inbound Telegram → edición ComfyUI (img2img) sin MLX-Vision."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from core.telegram_media_download import download_telegram_file_bytes

_log = logging.getLogger("duckclaw.gateway.comfyui_inbound")

COMFYUI_EDIT_TAG = "[COMFYUI_EDIT"


def comfyui_inbound_edit_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_COMFYUI_INBOUND_EDIT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def should_route_comfyui_edit(
    *,
    has_visual: bool,
    caption: str,
    media_group_id: str = "",
) -> bool:
    if not comfyui_inbound_edit_enabled():
        return False
    if not has_visual:
        return False
    if not (caption or "").strip():
        return False
    if (media_group_id or "").strip():
        return False
    return True


def build_comfyui_edit_manager_text(source_image_path: str, caption: str) -> str:
    cap = (caption or "").strip()
    path = (source_image_path or "").strip()
    return (
        f"{COMFYUI_EDIT_TAG} source_image_path={path}]\n"
        "El usuario envió una foto para EDITAR (no analizar). "
        f"Instrucciones: «{cap}».\n"
        "Debes llamar la tool edit_visual_asset con source_image_path exacto "
        "y edit_prompt en español con esas instrucciones.\n"
        "No uses VLM ni describas la imagen: solo edítala y confirma cuando la tool devuelva ok."
    )


async def ingest_comfyui_edit_inbound(
    *,
    bot_token: str,
    file_id: str,
    caption: str,
    tenant_id: str,
    mime_type: str = "image/jpeg",
) -> str:
    """
    Descarga foto Telegram, guarda en db/private/{tenant}/inbound/, retorna texto para el agente.
    Raises on download/save failure.
    """
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    raw = await download_telegram_file_bytes(bot_token, file_id)
    ext = ".jpg"
    mt = (mime_type or "").strip().lower()
    if mt == "image/png":
        ext = ".png"
    elif mt == "image/webp":
        ext = ".webp"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    elif raw[:2] == b"\xff\xd8":
        ext = ".jpg"

    inbound_dir = user_vault_dir(tid) / "inbound"
    inbound_dir.mkdir(parents=True, exist_ok=True)
    out_path = (inbound_dir / f"{uuid.uuid4()}{ext}").resolve()
    out_path.write_bytes(raw)
    _log.info(
        "comfyui_inbound saved tenant=%s path=%s bytes=%s",
        tid,
        out_path,
        len(raw),
    )
    return build_comfyui_edit_manager_text(str(out_path), caption)


def save_inbound_bytes_for_tenant(
    raw: bytes,
    tenant_id: str,
    *,
    mime_type: str = "image/jpeg",
) -> Path:
    """Guarda bytes ya descargados (tests o reutilización)."""
    from duckclaw.vaults import user_vault_dir

    tid = (tenant_id or "default").strip() or "default"
    ext = ".jpg"
    if (mime_type or "").strip().lower() == "image/png":
        ext = ".png"
    elif (mime_type or "").strip().lower() == "image/webp":
        ext = ".webp"
    inbound_dir = user_vault_dir(tid) / "inbound"
    inbound_dir.mkdir(parents=True, exist_ok=True)
    out_path = (inbound_dir / f"{uuid.uuid4()}{ext}").resolve()
    out_path.write_bytes(raw)
    return out_path
