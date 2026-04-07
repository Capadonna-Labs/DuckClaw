"""Troceo de texto plano para Telegram (sendMessage 4096), alineado con main._invoke_chat."""

from __future__ import annotations

import os
from typing import Any, Callable

# Telegram sendMessage: máx. 4096 caracteres (https://core.telegram.org/bots/api#sendmessage).
TELEGRAM_SENDMESSAGE_CHAR_LIMIT = 4096
_DEFAULT_TELEGRAM_REPLY_PLAIN_CHUNK = 2000


def telegram_reply_plain_chunk_size() -> int:
    """Trozos de texto plano; margen conservador para no superar 4096 tras escapar HTML."""
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_REPLY_CHUNK_PLAIN") or "").strip()
    if raw:
        try:
            return max(256, min(int(raw), TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 200))
        except ValueError:
            pass
    return _DEFAULT_TELEGRAM_REPLY_PLAIN_CHUNK


def split_plain_text_for_telegram_reply(text: str, max_chunk: int) -> list[str]:
    """Parte texto plano; cada parte se escapa aparte para n8n → Telegram (límite 4096)."""
    if max_chunk < 64:
        max_chunk = 64
    t = text or ""
    if not t:
        return [""]
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        if n - i <= max_chunk:
            out.append(t[i:n])
            break
        end = i + max_chunk
        window = t[i:end]
        nl = window.rfind("\n")
        if nl > 0:
            end = i + nl + 1
        out.append(t[i:end])
        i = end
    return out


def plain_subchunks_for_telegram_budget(plain: str, safe_fn: Any) -> list[str]:
    """Subdivide texto plano hasta que ``safe_fn`` (p. ej. escape HTML) no supere el límite de Telegram."""
    if not plain:
        return []
    cap = TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 32
    if len(safe_fn(plain)) <= cap:
        return [plain]
    if len(plain) <= 1:
        return [plain]
    mid = len(plain) // 2
    return plain_subchunks_for_telegram_budget(plain[:mid], safe_fn) + plain_subchunks_for_telegram_budget(
        plain[mid:], safe_fn
    )


def gateway_multipart_plain_head_tail(
    reply_plain_for_storage: str,
    safe_html_fn: Callable[[str], str],
) -> tuple[str | None, str | None]:
    """
    Misma lógica que ``_invoke_chat``: cabeza + cola para varios sendMessage si hace falta.
    Retorna (None, None) si basta un único mensaje (el caller debe usar el texto completo).
    """
    coarse = split_plain_text_for_telegram_reply(
        reply_plain_for_storage or "",
        telegram_reply_plain_chunk_size(),
    )
    plain_parts: list[str] = []
    for piece in coarse:
        plain_parts.extend(plain_subchunks_for_telegram_budget(piece, safe_html_fn))
    if not plain_parts:
        plain_parts = [""]
    if len(plain_parts) <= 1:
        return None, None
    tail_plain = "\n\n".join(plain_parts[1:])
    if not tail_plain.strip():
        return None, None
    return plain_parts[0], tail_plain
