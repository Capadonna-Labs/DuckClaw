"""
Envío de gráficos del sandbox al chat por Bot API.

sendPhoto rechaza a veces PNG grandes o con dimensiones extremas (HTTP 400);
sendDocument suele aceptar el mismo archivo (hasta 50 MB).
"""

from __future__ import annotations

import json
import logging
import uuid
from urllib import request as url_request
from urllib.error import HTTPError, URLError

_log = logging.getLogger("duckclaw.gateway")

# Nombre explícito en Content-Disposition (Telegram sendPhoto / sendDocument).
CHART_UPLOAD_FILENAME_PNG = "chart.png"
CHART_UPLOAD_FILENAME_JPEG = "chart.jpg"
CHART_UPLOAD_FILENAME_BIN = "chart.bin"

# No intentar sendPhoto con basura decodificada (evita IMAGE_PROCESS_FAILED y .bin).
_MIN_IMAGE_BYTES_FOR_TELEGRAM = 32


def _telegram_api_detail_for_log(detail: str) -> str:
    """Extrae error_code/description del JSON de Telegram para logs (no para el usuario)."""
    s = (detail or "").strip()
    if "{" not in s:
        return s[:2000]
    start = s.find("{")
    try:
        data = json.loads(s[start:])
    except json.JSONDecodeError:
        return s[:2000]
    if not isinstance(data, dict):
        return s[:2000]
    parts: list[str] = []
    if data.get("error_code") is not None:
        parts.append(f"error_code={data.get('error_code')}")
    desc = data.get("description")
    if isinstance(desc, str) and desc:
        parts.append(f"description={desc!r}")
    return " ".join(parts) if parts else s[:2000]


def _multipart_form_body(
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


def _sniff_image_meta(image_bytes: bytes) -> tuple[str, str]:
    if len(image_bytes) >= 8 and image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", CHART_UPLOAD_FILENAME_PNG
    if len(image_bytes) >= 2 and image_bytes[:2] == b"\xff\xd8":
        return "image/jpeg", CHART_UPLOAD_FILENAME_JPEG
    return "application/octet-stream", CHART_UPLOAD_FILENAME_BIN


def is_telegram_ready_image_bytes(image_bytes: bytes) -> bool:
    """True si los bytes son PNG o JPEG reconocibles (tamaño mínimo razonable)."""
    if not image_bytes or len(image_bytes) < _MIN_IMAGE_BYTES_FOR_TELEGRAM:
        return False
    ctype, _ = _sniff_image_meta(image_bytes)
    return ctype in ("image/png", "image/jpeg")


def _post_telegram_multipart(
    *,
    bot_token: str,
    api_method: str,
    chat_id: str,
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    timeout_sec: int = 120,
) -> tuple[bool, str]:
    boundary = f"----duckclaw{uuid.uuid4().hex}"
    body = _multipart_form_body(
        boundary,
        [("chat_id", str(chat_id).strip())],
        [(file_field, filename, file_bytes, content_type)],
    )
    url = f"https://api.telegram.org/bot{bot_token.strip()}/{api_method}"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = url_request.Request(url, data=body, headers=headers, method="POST")
    try:
        with url_request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {raw}"
    except URLError as exc:
        return False, f"URLError: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    try:
        data = json.loads(raw) if raw.strip().startswith("{") else {}
    except json.JSONDecodeError:
        return False, raw[:2000]
    if isinstance(data, dict) and data.get("ok") is True:
        return True, raw
    return False, raw[:2000]


def send_sandbox_chart_to_telegram_sync(*, bot_token: str, chat_id: str, image_bytes: bytes) -> bool:
    """
    Intenta sendPhoto; si falla (p. ej. 400 por tamaño/dimensiones), reintenta sendDocument.
    """
    cid = str(chat_id or "").strip()
    if not cid or not image_bytes:
        return False
    if not is_telegram_ready_image_bytes(image_bytes):
        _log.warning(
            "sandbox chart: se omiten sendPhoto/sendDocument (bytes no son PNG/JPEG válidos, len=%s)",
            len(image_bytes),
        )
        return False
    ctype, filename = _sniff_image_meta(image_bytes)

    ok, detail = _post_telegram_multipart(
        bot_token=bot_token,
        api_method="sendPhoto",
        chat_id=cid,
        file_field="photo",
        filename=filename,
        file_bytes=image_bytes,
        content_type="image/png" if ctype == "image/png" else "image/jpeg",
    )
    if ok:
        _log.info("sandbox chart: sendPhoto OK chat_id=%s file=%s", cid, filename)
        return True

    human = _telegram_api_detail_for_log(detail)
    _log.warning(
        "Telegram sendPhoto falló (chat_id=%s, bytes=%s, file=%s, Content-Type=%s). "
        "Resumen API: %s | cuerpo bruto: %s",
        cid,
        len(image_bytes),
        filename,
        ctype,
        human,
        detail[:1200],
    )
    _log.info("sandbox chart: reintentando con sendDocument (adjunto descargable si sendPhoto no aplica).")

    ok_doc, detail_doc = _post_telegram_multipart(
        bot_token=bot_token,
        api_method="sendDocument",
        chat_id=cid,
        file_field="document",
        filename=filename,
        file_bytes=image_bytes,
        content_type="image/png" if ctype == "image/png" else "image/jpeg",
    )
    if ok_doc:
        _log.info("sandbox chart: sendDocument OK chat_id=%s file=%s", cid, filename)
        return True

    _log.warning(
        "Telegram sendDocument falló (chat_id=%s). Resumen API: %s | cuerpo: %s",
        cid,
        _telegram_api_detail_for_log(detail_doc),
        detail_doc[:1200],
    )
    return False
