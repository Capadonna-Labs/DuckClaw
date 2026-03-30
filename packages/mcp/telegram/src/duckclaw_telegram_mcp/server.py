"""Servidor MCP stdio: herramientas Telegram."""

from __future__ import annotations

import json
import logging
import os

from duckclaw_telegram_mcp.image_b64 import decode_valid_sandbox_image_bytes

from duckclaw_telegram_mcp.telegram_api import send_message_api, send_photo_or_document_api

_log = logging.getLogger("duckclaw.telegram_mcp")


def _setup_logging() -> None:
    level = (os.getenv("DUCKCLAW_TELEGRAM_MCP_LOG_LEVEL") or "INFO").strip().upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(message)s")


def build_mcp_app():
    """FastMCP app con tools del spec."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Instala el paquete 'mcp' (pip/uv install mcp)") from exc

    mcp = FastMCP("duckclaw-telegram")

    @mcp.tool()
    def telegram_send_message(chat_id: str, text: str, parse_mode: str = "MarkdownV2") -> str:
        """Envía un mensaje de texto a un chat de Telegram."""
        if parse_mode not in ("MarkdownV2", "HTML", ""):
            parse_mode = "MarkdownV2"
        r = send_message_api(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return json.dumps(r, ensure_ascii=False)

    @mcp.tool()
    def telegram_send_photo(
        chat_id: str,
        photo_base64: str,
        filename: str = "chart.png",
        caption: str = "",
    ) -> str:
        """Envía una imagen (base64) a Telegram. Valida PNG/JPEG; filename por defecto chart.png."""
        raw = decode_valid_sandbox_image_bytes(photo_base64)
        if not raw:
            return json.dumps({"ok": False, "error": "photo_base64 no decodifica a PNG/JPEG válido"}, ensure_ascii=False)
        cap = (caption or "").strip() or None
        r = send_photo_or_document_api(
            chat_id=chat_id,
            image_bytes=raw,
            filename=filename or "chart.png",
            caption=cap,
        )
        return json.dumps(r, ensure_ascii=False)

    return mcp


def main() -> None:
    _setup_logging()
    if not (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
        _log.error("TELEGRAM_BOT_TOKEN es obligatorio para duckclaw-telegram-mcp")
        raise SystemExit(2)
    app = build_mcp_app()
    app.run()
