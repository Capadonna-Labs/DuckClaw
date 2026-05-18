"""Tests adjuntos de imagen en playground admin."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_GW_DIR = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_GW_DIR) not in sys.path:
    sys.path.insert(0, str(_GW_DIR))

# 1x1 PNG
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_decode_admin_image_b64() -> None:
    from core.vlm_ingest import decode_admin_image_b64

    raw = decode_admin_image_b64(_TINY_PNG_B64)
    assert len(raw) > 0
    data_url = f"data:image/png;base64,{_TINY_PNG_B64}"
    assert len(decode_admin_image_b64(data_url)) > 0


def test_decode_rejects_invalid_b64() -> None:
    from core.vlm_ingest import decode_admin_image_b64

    with pytest.raises(ValueError, match="inválido"):
        decode_admin_image_b64("not-valid-base64!!!")


def test_enrich_message_with_admin_images_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    from core import vlm_ingest as vlm

    async def _fake_single(**_kwargs):
        return {
            "vlm_summary": "cuadro rojo",
            "image_hash": "abc",
            "confidence_score": 0.9,
        }

    monkeypatch.setattr(vlm, "run_vlm_on_image_bytes", _fake_single)

    async def _run():
        return await vlm.enrich_message_with_admin_images(
            "¿Qué ves?",
            [{"mime_type": "image/png", "data_base64": _TINY_PNG_B64}],
        )

    out = asyncio.run(_run())
    assert "¿Qué ves?" in out
    assert "Contexto visual adjunto" in out
    assert "cuadro rojo" in out


def test_playground_chat_requires_message_or_images(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "default", "message": "", "images": []},
    )
    assert r.status_code == 422


def test_playground_chat_with_images_mock_vlm(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import vlm_ingest as vlm

    async def _fake_enrich(message: str, images):
        return f"{message}\nContexto visual adjunto: mock summary"

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _fake_enrich)

    import main as gateway_main

    async def _fake_invoke(*_a, **_k):
        return {"response": "ok", "assigned_worker_id": "default"}

    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")

    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "message": "describe",
            "chat_id": "admin-playground",
            "images": [{"mime_type": "image/png", "data_base64": _TINY_PNG_B64}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_playground_chat_invalid_mime(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "message": "x",
            "images": [{"mime_type": "image/gif", "data_base64": _TINY_PNG_B64}],
        },
    )
    assert r.status_code == 400
