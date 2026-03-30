"""telegram_media_upload: detección MIME y multipart (sin llamar a Telegram)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_GW = _REPO / "services" / "api-gateway"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))

from core.telegram_media_upload import (  # noqa: E402
    _sniff_image_meta,
    _telegram_api_detail_for_log,
    send_sandbox_chart_to_telegram_sync,
)


def test_sniff_png() -> None:
    from core.telegram_media_upload import CHART_UPLOAD_FILENAME_PNG

    b = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert _sniff_image_meta(b) == ("image/png", CHART_UPLOAD_FILENAME_PNG)
    assert CHART_UPLOAD_FILENAME_PNG == "chart.png"


def test_telegram_api_detail_for_log_parses_json() -> None:
    raw = 'HTTP 400: {"ok":false,"error_code":400,"description":"Bad Request: IMAGE_PROCESS_FAILED"}'
    s = _telegram_api_detail_for_log(raw)
    assert "error_code=400" in s
    assert "IMAGE_PROCESS_FAILED" in s


def test_sniff_jpeg() -> None:
    from core.telegram_media_upload import CHART_UPLOAD_FILENAME_JPEG

    b = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    assert _sniff_image_meta(b) == ("image/jpeg", CHART_UPLOAD_FILENAME_JPEG)


def test_send_sandbox_chart_skips_non_image_without_http() -> None:
    """Bytes que no son PNG/JPEG no deben llamar a la API (retorno temprano)."""
    assert send_sandbox_chart_to_telegram_sync(bot_token="dummy", chat_id="1", image_bytes=b"not-an-image") is False
