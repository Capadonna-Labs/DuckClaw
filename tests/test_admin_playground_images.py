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


def test_playground_chat_with_images_routes_edit_inbound(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def _fake_ingest(**kwargs):
        captured.update(kwargs)
        return "[COMFYUI_EDIT source_image_path=/tmp/x.jpg]\nedit"

    from core import comfyui_inbound as ci
    from core import vlm_ingest as vlm

    monkeypatch.setattr(ci, "ingest_admin_visual_edit_inbound", _fake_ingest)

    async def _fake_enrich(_message: str, _images):
        raise AssertionError("Comfy edit route should bypass VLM enrichment")

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _fake_enrich)

    import routers.admin as admin_router
    import routers.admin_domains.playground.chat_turn as playground_chat_turn
    from test_admin_router import _mock_playground_team

    seen: dict = {}

    async def _fake_invoke(chat, *_a, **_k):
        seen["message"] = chat.message
        return {"response": "ok", "assigned_worker_id": "default"}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)
    monkeypatch.setenv("DUCKCLAW_COMFYUI_INBOUND_EDIT", "1")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")

    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "message": "Haz la ropa amarilla",
            "chat_id": "admin-playground",
            "images": [{"mime_type": "image/png", "data_base64": _TINY_PNG_B64}],
        },
    )
    assert r.status_code == 200, r.text
    assert "COMFYUI_EDIT" in seen.get("message", "")
    assert captured.get("caption") == "Haz la ropa amarilla"


def test_playground_chat_with_images_mock_vlm(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import vlm_ingest as vlm

    async def _fake_enrich(message: str, images, **_kwargs):
        return f"{message}\nContexto visual adjunto: mock summary"

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _fake_enrich)

    import routers.admin_domains.playground.chat_turn as playground_chat_turn
    import routers.admin_domains.playground_chat as playground_chat_router
    from test_admin_router import _mock_playground_team

    async def _fake_invoke(*_a, **_k):
        return {"response": "ok", "assigned_worker_id": "default"}

    monkeypatch.setattr(
        playground_chat_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")

    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "message": "compara estas",
            "chat_id": "admin-playground",
            "images": [
                {"mime_type": "image/png", "data_base64": _TINY_PNG_B64},
                {"mime_type": "image/png", "data_base64": _TINY_PNG_B64},
            ],
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


def test_playground_fly_command_skips_vlm_with_images(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import vlm_ingest as vlm

    async def _fail_enrich(*_a, **_k):
        raise AssertionError("VLM must not run for fly commands")

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _fail_enrich)

    import routers.admin_domains.playground.chat_turn as playground_chat_turn
    import routers.admin_domains.playground_chat as playground_chat_router
    from test_admin_router import _mock_playground_team

    async def _fake_invoke(*_a, **_k):
        return {"response": "fly-ok", "assigned_worker_id": "default"}

    monkeypatch.setattr(
        playground_chat_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")

    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "user_incoming": "/loop --status",
            "message": "[KNOWLEDGE_SCOPE]\nscope\n[/KNOWLEDGE_SCOPE]\n/loop --status",
            "chat_id": "admin-playground",
            "images": [{"mime_type": "image/png", "data_base64": _TINY_PNG_B64}],
        },
    )
    assert r.status_code == 200, r.text


def test_playground_vlm_all_failed_degrades_instead_of_502(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import vlm_ingest as vlm

    async def _raise_all_failed(*_a, **_k):
        raise vlm.VlmIngestAllFailed(RuntimeError("mlx down"))

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _raise_all_failed)

    import routers.admin_domains.playground.chat_turn as playground_chat_turn
    import routers.admin_domains.playground_chat as playground_chat_router
    from test_admin_router import _mock_playground_team

    seen: dict[str, str] = {}

    async def _fake_invoke(prepared, *_a, **_k):
        seen["message"] = prepared.msg
        return {"response": "ok", "assigned_worker_id": "default"}

    monkeypatch.setattr(
        playground_chat_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)
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
    assert "VLM" in seen.get("message", "") or "visión" in seen.get("message", "")
