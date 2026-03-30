# packages/shared/src/duckclaw/integrations/telegram/telegram_outbound_sync.py
"""Envío síncrono a la Bot API (urllib): heartbeat, sandbox ping, fallback sin httpx async."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2

_log = logging.getLogger("duckclaw.telegram_outbound_sync")

_DEFAULT_PLAIN_CHUNK = 3600


def normalize_telegram_chat_id_for_bot_api(chat_id: str | None) -> str:
    """Extrae id numérico si el gateway mandó etiqueta tipo «@User (1726618406)»."""
    s = str(chat_id or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"-?\d+", s):
        return s
    m = re.search(r"\((-?\d+)\)\s*$", s)
    if m:
        return m.group(1)
    m = re.search(r"-?\d{5,}", s)
    if m:
        return m.group(0)
    return s


def send_message_markdown_v2_sync(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    timeout_sec: float = 60.0,
    log: logging.Logger | None = None,
    emit_success_log: bool = True,
) -> bool:
    """Un sendMessage con parse_mode MarkdownV2. Devuelve True si ``ok`` en la respuesta JSON."""
    lg = log or _log
    token = (bot_token or "").strip()
    cid = normalize_telegram_chat_id_for_bot_api(chat_id) or (chat_id or "").strip()
    body = (text or "").strip()
    if not token or not cid or not body:
        lg.warning(
            "telegram native sendMessage omitido: token=%s chat_id=%s text_len=%s",
            bool(token),
            cid or chat_id,
            len(body),
        )
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": cid,
        "text": body,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:1200]
        except Exception:
            pass
        lg.warning(
            "telegram native sendMessage HTTP error chat_id=%s code=%s body=%r",
            cid,
            exc.code,
            err_body,
        )
        return False
    except URLError as exc:
        lg.warning("telegram native sendMessage URLError chat_id=%s: %s", cid, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        lg.warning("telegram native sendMessage error chat_id=%s: %s", cid, exc)
        return False
    try:
        dec = json.loads(raw) if raw.strip().startswith("{") else {}
    except json.JSONDecodeError:
        lg.warning("telegram native sendMessage JSON inválido chat_id=%s raw=%r", cid, raw[:400])
        return False
    ok = bool(isinstance(dec, dict) and dec.get("ok") is True)
    if ok:
        if emit_success_log:
            lg.info(
                "telegram native sendMessage OK chat_id=%s text_len=%s",
                cid,
                len(body),
            )
    else:
        lg.warning(
            "telegram native sendMessage API ok=false chat_id=%s response=%r",
            cid,
            raw[:800],
        )
    return ok


def send_long_plain_text_markdown_v2_chunks_sync(
    *,
    bot_token: str,
    chat_id: str,
    plain_text: str,
    max_plain_chunk: int = _DEFAULT_PLAIN_CHUNK,
    timeout_sec: float = 60.0,
    log: logging.Logger | None = None,
) -> int:
    """
    Trocea texto plano, escapa MarkdownV2 y envía uno o varios sendMessage.
    Returns: número de partes enviadas con éxito.
    """
    lg = log or _log
    raw = (plain_text or "").strip()
    if not raw:
        return 0
    token = (bot_token or "").strip()
    cid = normalize_telegram_chat_id_for_bot_api(chat_id) or (chat_id or "").strip()
    if not token or not cid:
        lg.warning("telegram native chunks omitidos: token=%s chat_id=%s", bool(token), cid or chat_id)
        return 0
    cap = max(256, min(max_plain_chunk, 3900))
    chunks: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        chunks.append(raw[i : i + cap])
        i += cap
    if not chunks:
        chunks = [raw]
    total = len(chunks)
    sent = 0
    for idx, part in enumerate(chunks):
        prefix = f"[{idx + 1}/{total}]\n" if total > 1 else ""
        escaped = escape_telegram_markdown_v2(prefix + part)
        lg.info(
            "telegram native chunk %s/%s chat_id=%s plain_len=%s escaped_len=%s",
            idx + 1,
            total,
            cid,
            len(part),
            len(escaped),
        )
        if send_message_markdown_v2_sync(
            bot_token=token,
            chat_id=cid,
            text=escaped,
            timeout_sec=timeout_sec,
            log=lg,
            emit_success_log=False,
        ):
            sent += 1
    if sent < total:
        lg.warning(
            "telegram native chunks: solo %s/%s partes OK chat_id=%s",
            sent,
            total,
            cid,
        )
    else:
        lg.info("telegram native chunks completado OK chat_id=%s partes=%s", cid, total)
    return sent
