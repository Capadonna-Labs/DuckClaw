"""Decodificación tolerante de figure_base64 (sandbox → Telegram sendPhoto)."""

from __future__ import annotations

import base64


def decode_sandbox_figure_base64(photo_b64: str | bytes) -> bytes:
    """
    Evita fallos típicos: espacios/saltos de línea, prefijo data URL, padding incorrecto,
    alfabeto URL-safe (- _).
    """
    if isinstance(photo_b64, (bytes, bytearray)):
        try:
            photo_b64 = bytes(photo_b64).decode("ascii")
        except UnicodeDecodeError:
            return b""
    if not isinstance(photo_b64, str) or not photo_b64.strip():
        return b""
    s = photo_b64.strip()
    if s.lower().startswith("data:") and "," in s:
        s = s.split(",", 1)[1].strip()
    s = "".join(s.split())
    s = s.replace("-", "+").replace("_", "/")
    s = s.rstrip("=")
    rem = len(s) % 4
    if rem:
        s += "=" * (4 - rem)
    try:
        return base64.b64decode(s, validate=False)
    except Exception:
        return b""


def decode_valid_sandbox_image_bytes(photo_b64: str | bytes) -> bytes:
    """
    Decodifica y devuelve bytes solo si parecen PNG o JPEG (evita enviar basura a Telegram).
    """
    raw = decode_sandbox_figure_base64(photo_b64)
    if len(raw) < 32:
        return b""
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    if len(raw) >= 2 and raw[:2] == b"\xff\xd8":
        return raw
    return b""
