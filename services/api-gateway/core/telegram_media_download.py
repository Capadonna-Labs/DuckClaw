"""Descarga de archivos Telegram (getFile) sin depender de vlm_ingest / MLX."""

from __future__ import annotations

import os

import httpx

_DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def max_telegram_image_bytes() -> int:
    try:
        return int(os.environ.get("DUCKCLAW_TELEGRAM_MAX_IMAGE_BYTES") or str(_DEFAULT_MAX_IMAGE_BYTES))
    except ValueError:
        return _DEFAULT_MAX_IMAGE_BYTES


async def download_telegram_file_bytes(bot_token: str, file_id: str) -> bytes:
    """
    Descarga bytes de un file_id de Telegram Bot API.
    Raises RuntimeError si getFile falla o el archivo excede el límite de tamaño.
    """
    token = (bot_token or "").strip()
    fid = (file_id or "").strip()
    if not token or not fid:
        raise ValueError("bot_token o file_id vacío")
    api = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        r = await client.get(f"{api}/getFile", params={"file_id": fid})
        r.raise_for_status()
        data = r.json() if r.content else {}
        if not data.get("ok") or not isinstance(data.get("result"), dict):
            raise RuntimeError("Telegram getFile failed")
        file_path = str(data["result"].get("file_path") or "").strip()
        if not file_path:
            raise RuntimeError("Telegram file_path vacío")
        rf = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
        rf.raise_for_status()
        raw = bytes(rf.content or b"")
    limit = max_telegram_image_bytes()
    if len(raw) > limit:
        raise RuntimeError(f"imagen demasiado grande ({len(raw)} > {limit})")
    return raw
