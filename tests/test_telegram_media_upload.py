"""telegram_media_upload: detección MIME y multipart (sin llamar a Telegram)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_GW = _REPO / "services" / "api-gateway"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))

import pytest

from core.telegram_media_upload import (  # noqa: E402
    _sniff_image_meta,
    _telegram_api_detail_for_log,
    send_sandbox_chart_to_telegram_sync,
    send_sandbox_charts_to_telegram_sync,
    send_sandbox_documents_to_telegram_sync,
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


def test_send_sandbox_charts_calls_sendphoto_per_image(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64

    png = b"\x89PNG\r\n\x1a\n" + b"y" * 80
    b64_1 = base64.b64encode(png).decode("ascii")

    calls: list[bool] = []

    def _fake_send(**kwargs: object) -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(
        "core.telegram_media_upload.send_sandbox_chart_to_telegram_sync",
        _fake_send,
    )
    n = send_sandbox_charts_to_telegram_sync(bot_token="t", chat_id="1", images_b64=[b64_1, b64_1])
    assert n == 2
    assert len(calls) == 2


def test_send_sandbox_documents_skips_path_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.telegram_media_upload as tmu

    root = tmp_path / "output" / "sandbox"
    root.mkdir(parents=True)
    good = root / "plan.csv"
    good.write_text("a,b\n1,2", encoding="utf-8")
    calls: list[str] = []

    def _fake_post(**kwargs: object) -> tuple[bool, str]:
        fn = kwargs.get("filename")
        calls.append(str(fn) if fn is not None else "")
        return True, '{"ok":true}'

    monkeypatch.setattr(tmu, "_post_telegram_multipart", _fake_post)
    monkeypatch.setenv("DUCKCLAW_SANDBOX_ARTIFACT_ROOT", str(root))
    n = send_sandbox_documents_to_telegram_sync(
        bot_token="t",
        chat_id="1",
        paths=[str(good), "/etc/passwd"],
    )
    assert n == 1
    assert calls == ["plan.csv"]
