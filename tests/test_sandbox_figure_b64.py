"""Decodificación base64 tolerante para PNG del sandbox (gateway → Telegram)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_GW = _REPO / "services" / "api-gateway"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))

from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes


def test_decode_strips_whitespace_and_repads() -> None:
    raw = b"\x89PNG\r\n\x1a\n" + b"x" * 200
    enc = base64.b64encode(raw).decode("ascii")
    messy = "  " + enc[:80] + "\n" + enc[80:160] + "  \n  " + enc[160:]
    messy = messy.rstrip("=")  # quitar padding a propósito
    out = decode_sandbox_figure_base64(messy)
    assert out == raw


def test_decode_data_url_prefix() -> None:
    raw = b"\xff\xd8\xff\xe0" + b"0" * 20
    enc = base64.b64encode(raw).decode("ascii")
    out = decode_sandbox_figure_base64(f"data:image/jpeg;base64,{enc}")
    assert out == raw


def test_decode_valid_rejects_random_payload() -> None:
    enc = base64.b64encode(b"hello").decode("ascii")
    assert decode_valid_sandbox_image_bytes(enc) == b""
