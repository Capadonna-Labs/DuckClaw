"""Cliente HTTP síncrono mínimo para Bot API (urllib)."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duckclaw.integrations.telegram.telegram_outbound_sync import normalize_telegram_chat_id_for_bot_api
from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2, llm_markdown_to_telegram_html

from duckclaw_telegram_mcp.rate_limit import pace_before_request, retry_after_sec_from_telegram_body

_log = logging.getLogger("duckclaw.telegram_mcp")

# Telegram: fotos hasta ~10 MB (sendPhoto); por encima usar sendDocument.
_TELEGRAM_SEND_PHOTO_MAX_BYTES = 10 * 1024 * 1024


def _multipart_body(
    boundary: str,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, bytes, str]],
) -> bytes:
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(f"--{boundary}".encode("ascii") + crlf)
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode("ascii") + crlf + crlf)
        parts.append(str(value).encode("utf-8") + crlf)
    for name, filename, content, ctype in files:
        parts.append(f"--{boundary}".encode("ascii") + crlf)
        disp = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'
        parts.append(disp.encode("ascii") + crlf)
        parts.append(f"Content-Type: {ctype}".encode("ascii") + crlf + crlf)
        parts.append(content + crlf)
    parts.append(f"--{boundary}--".encode("ascii") + crlf)
    return b"".join(parts)


def _post_json(
    bot_token: str,
    method: str,
    payload: dict[str, Any],
    *,
    timeout: float = 120.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token.strip()}/{method}"
    attempt = 0
    last_err = ""
    while attempt <= max_retries:
        pace_before_request()
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                wait = retry_after_sec_from_telegram_body(raw) or min(2.0 * (attempt + 1), 60.0)
                _log.warning("telegram MCP: 429 %s esperando %.1fs (intento %s)", method, wait, attempt + 1)
                time.sleep(wait)
                attempt += 1
                last_err = raw[:2000]
                continue
            return {"ok": False, "error": f"HTTP {exc.code}: {raw[:800]}"}
        except URLError as exc:
            return {"ok": False, "error": f"URLError: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        try:
            decoded = json.loads(raw) if raw.strip().startswith("{") else {}
        except json.JSONDecodeError:
            return {"ok": False, "error": raw[:2000]}
        if isinstance(decoded, dict) and decoded.get("ok") is True:
            return decoded
        if isinstance(decoded, dict):
            desc = str(decoded.get("description") or "")
            if "429" in raw or "Too Many Requests" in desc:
                wait = retry_after_sec_from_telegram_body(raw) or min(2.0 * (attempt + 1), 60.0)
                time.sleep(wait)
                attempt += 1
                last_err = raw[:2000]
                continue
        return {"ok": False, "error": raw[:2000] if raw else "empty response"}
    return {"ok": False, "error": last_err or "max_retries"}


def send_message_api(
    *,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> dict[str, Any]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN no definido"}
    cid = normalize_telegram_chat_id_for_bot_api(chat_id) or chat_id.strip()
    if parse_mode not in ("MarkdownV2", "HTML", ""):
        parse_mode = "HTML"

    body_text = text
    payload: dict[str, Any] = {
        "chat_id": cid,
        "disable_web_page_preview": True,
    }
    if parse_mode == "MarkdownV2":
        payload["text"] = escape_telegram_markdown_v2(body_text)
        payload["parse_mode"] = "MarkdownV2"
    elif parse_mode == "HTML":
        payload["text"] = llm_markdown_to_telegram_html(body_text)
        payload["parse_mode"] = "HTML"
    else:
        payload["text"] = body_text

    out = _post_json(token, "sendMessage", payload)
    if isinstance(out, dict) and out.get("ok") is True:
        res = out.get("result")
        mid = res.get("message_id") if isinstance(res, dict) else None
        _log.info("telegram MCP: sendMessage OK chat_id=%s message_id=%s", cid, mid)
        return {"ok": True, "message_id": mid, "result": out}
    err = str(out.get("error", out)) if isinstance(out, dict) else str(out)
    _log.warning("telegram MCP: sendMessage fail chat_id=%s %s", cid, err[:500])
    return {"ok": False, "error": err}


def _sniff_filename_and_ctype(image_bytes: bytes, default_filename: str) -> tuple[str, str]:
    if len(image_bytes) >= 8 and image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        fn = default_filename if default_filename.lower().endswith(".png") else "chart.png"
        return fn, "image/png"
    if len(image_bytes) >= 2 and image_bytes[:2] == b"\xff\xd8":
        base = default_filename.rsplit(".", 1)[0] if "." in default_filename else default_filename
        return f"{base}.jpg", "image/jpeg"
    return default_filename, "application/octet-stream"


def send_photo_or_document_api(
    *,
    chat_id: str,
    image_bytes: bytes,
    filename: str = "chart.png",
    caption: str | None = None,
) -> dict[str, Any]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN no definido"}
    cid = normalize_telegram_chat_id_for_bot_api(chat_id) or chat_id.strip()
    if len(image_bytes) < 32:
        return {"ok": False, "error": "imagen demasiado pequeña o vacía"}

    fname, ctype = _sniff_filename_and_ctype(image_bytes, filename.strip() or "chart.png")
    if ctype == "application/octet-stream":
        return {"ok": False, "error": "payload no es PNG/JPEG válido"}

    use_document = len(image_bytes) > _TELEGRAM_SEND_PHOTO_MAX_BYTES
    method = "sendDocument" if use_document else "sendPhoto"
    field = "document" if use_document else "photo"

    def _one_multipart(api_method: str, file_field: str) -> dict[str, Any]:
        boundary = f"----duckclawmcp{uuid.uuid4().hex}"
        fields: list[tuple[str, str]] = [("chat_id", cid)]
        if caption and caption.strip():
            fields.append(("caption", caption.strip()[:1024]))
        body = _multipart_body(
            boundary,
            fields,
            [(file_field, fname, image_bytes, ctype)],
        )
        url = f"https://api.telegram.org/bot{token.strip()}/{api_method}"
        attempt = 0
        while attempt <= 3:
            pace_before_request()
            req = Request(
                url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            try:
                with urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            except HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429:
                    wait = retry_after_sec_from_telegram_body(raw) or 2.0 * (attempt + 1)
                    time.sleep(min(wait, 60.0))
                    attempt += 1
                    continue
                return {"ok": False, "error": f"HTTP {exc.code}: {raw[:800]}"}
            except URLError as exc:
                return {"ok": False, "error": f"URLError: {exc}"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
            try:
                data = json.loads(raw) if raw.strip().startswith("{") else {}
            except json.JSONDecodeError:
                return {"ok": False, "error": raw[:2000]}
            if isinstance(data, dict) and data.get("ok") is True:
                msg = data.get("result") if isinstance(data.get("result"), dict) else {}
                mid = msg.get("message_id") if isinstance(msg, dict) else None
                return {"ok": True, "message_id": mid, "result": data}
            if isinstance(data, dict) and "retry_after" in str(data):
                time.sleep(2.0)
                attempt += 1
                continue
            return {"ok": False, "error": raw[:2000]}
        return {"ok": False, "error": "max_retries multipart"}

    first = _one_multipart(method, field)
    if first.get("ok"):
        _log.info("telegram MCP: %s OK chat_id=%s bytes=%s", method, cid, len(image_bytes))
        return first

    if not use_document and method == "sendPhoto":
        _log.warning("telegram MCP: sendPhoto falló, reintento sendDocument chat_id=%s", cid)
        return _one_multipart("sendDocument", "document")

    return first
