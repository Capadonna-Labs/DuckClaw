"""
Envío de gráficos del sandbox al chat por Bot API.

sendPhoto rechaza a veces PNG grandes o con dimensiones extremas (HTTP 400);
sendDocument suele aceptar el mismo archivo (hasta 50 MB).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from urllib import request as url_request
from urllib.error import HTTPError, URLError

_log = logging.getLogger("duckclaw.gateway")

# Nombre explícito en Content-Disposition (Telegram sendPhoto / sendDocument).
CHART_UPLOAD_FILENAME_PNG = "chart.png"
CHART_UPLOAD_FILENAME_JPEG = "chart.jpg"
CHART_UPLOAD_FILENAME_BIN = "chart.bin"

# No intentar sendPhoto con basura decodificada (evita IMAGE_PROCESS_FAILED y .bin).
_MIN_IMAGE_BYTES_FOR_TELEGRAM = 32
# Margen bajo el límite ~50 MiB de Telegram para sendDocument.
_MAX_SANDBOX_DOCUMENT_BYTES = 48 * 1024 * 1024


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


def send_sandbox_chart_to_telegram_sync(
    *,
    bot_token: str,
    chat_id: str,
    image_bytes: bytes,
    upload_filename: str | None = None,
) -> bool:
    """
    Intenta sendPhoto; si falla (p. ej. 400 por tamaño/dimensiones), reintenta sendDocument.
    ``upload_filename``: nombre en multipart (p. ej. chart_2.png); por defecto chart.png / chart.jpg.
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
    if upload_filename and upload_filename.strip():
        filename = upload_filename.strip()

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


def _sandbox_telegram_artifact_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_SANDBOX_ARTIFACT_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "output" / "sandbox").resolve()


def _is_allowed_sandbox_document_path(path: Path, allowed_root: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
        root = allowed_root.resolve()
        resolved.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _content_type_for_sandbox_document(suffix: str) -> str:
    s = (suffix or "").lower()
    if s == ".md":
        return "text/markdown; charset=utf-8"
    if s == ".txt":
        return "text/plain; charset=utf-8"
    if s == ".csv":
        return "text/csv; charset=utf-8"
    if s == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def _max_sandbox_docs_per_telegram_delivery() -> int:
    raw = (os.environ.get("DUCKCLAW_SANDBOX_TELEGRAM_MAX_DOCS") or "20").strip()
    try:
        return max(1, min(int(raw), 50))
    except ValueError:
        return 20


def send_sandbox_documents_to_telegram_sync(
    *,
    bot_token: str,
    chat_id: str,
    paths: list[str],
    max_docs: int | None = None,
    max_bytes: int | None = None,
) -> int:
    """
    Envía cada ruta existente y permitida como sendDocument (basename como nombre de fichero).
    Retorna cuántos envíos tuvieron éxito.
    """
    cid = str(chat_id or "").strip()
    tok = (bot_token or "").strip()
    if not cid or not paths or not tok:
        return 0
    cap = max_docs if max_docs is not None else _max_sandbox_docs_per_telegram_delivery()
    limit = max_bytes if max_bytes is not None else _MAX_SANDBOX_DOCUMENT_BYTES
    root = _sandbox_telegram_artifact_root()
    sent = 0
    for raw_path in paths[:cap]:
        p = Path(str(raw_path).strip())
        if not p.name:
            continue
        if not _is_allowed_sandbox_document_path(p, root):
            _log.warning(
                "sandbox document: ruta fuera de la raíz permitida (omitida): %s root=%s",
                p,
                root,
            )
            continue
        if not p.is_file():
            _log.warning("sandbox document: omitido (no fichero o no existe): %s", p)
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if sz > limit:
            _log.warning("sandbox document: omitido (len=%s > max=%s): %s", sz, limit, p)
            continue
        try:
            body = p.read_bytes()
        except OSError as exc:
            _log.warning("sandbox document: lectura fallida %s: %s", p, exc)
            continue
        fname = p.name
        ctype = _content_type_for_sandbox_document(p.suffix)
        ok, detail = _post_telegram_multipart(
            bot_token=tok,
            api_method="sendDocument",
            chat_id=cid,
            file_field="document",
            filename=fname,
            file_bytes=body,
            content_type=ctype,
        )
        if ok:
            _log.info("sandbox document: sendDocument OK chat_id=%s file=%s", cid, fname)
            sent += 1
        else:
            _log.warning(
                "sandbox document: sendDocument falló chat_id=%s file=%s %s",
                cid,
                fname,
                _telegram_api_detail_for_log(detail),
            )
    return sent


def _max_sandbox_charts_per_telegram_delivery() -> int:
    raw = (os.environ.get("DUCKCLAW_SANDBOX_TELEGRAM_MAX_CHARTS") or "20").strip()
    try:
        return max(1, min(int(raw), 50))
    except ValueError:
        return 20


def send_sandbox_charts_to_telegram_sync(
    *,
    bot_token: str,
    chat_id: str,
    images_b64: list[str],
    max_charts: int | None = None,
) -> int:
    """
    Envía cada imagen válida con sendPhoto (o sendDocument como fallback), en orden.
    Retorna cuántas entregas tuvieron éxito.
    """
    from core.sandbox_figure_b64 import decode_valid_sandbox_image_bytes

    cap = max_charts if max_charts is not None else _max_sandbox_charts_per_telegram_delivery()
    sent = 0
    for idx, photo_b64 in enumerate(images_b64[:cap]):
        b64s = (photo_b64 or "").strip()
        if not b64s:
            continue
        png_bytes = decode_valid_sandbox_image_bytes(b64s)
        if not is_telegram_ready_image_bytes(png_bytes):
            _log.warning(
                "sandbox chart [%s]: base64 no produce PNG/JPEG válido (omitido)",
                idx + 1,
            )
            continue
        ctype_sniff, default_name = _sniff_image_meta(png_bytes)
        ext = ".png" if ctype_sniff == "image/png" else ".jpg" if ctype_sniff == "image/jpeg" else ".bin"
        upload_name = f"chart_{idx + 1}{ext}" if ext != ".bin" else f"chart_{idx + 1}_{default_name}"
        if send_sandbox_chart_to_telegram_sync(
            bot_token=bot_token,
            chat_id=chat_id,
            image_bytes=png_bytes,
            upload_filename=upload_name,
        ):
            sent += 1
    return sent
