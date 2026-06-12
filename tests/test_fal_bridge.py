"""Tests Fal bridge (mock async pipeline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from duckclaw.forge.skills import fal_bridge


class _FakeDb:
    _read_only = False

    def execute(self, sql: str) -> None:
        pass

    def query(self, sql: str):
        return json.dumps([{"total": 0.0}])


@pytest.fixture(autouse=True)
def _env_fal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    monkeypatch.setenv("DUCKCLAW_MEDIA_DAILY_BUDGET_USD", "5.0")


def test_register_fal_skill_adds_four_tools() -> None:
    tools: list[Any] = []
    fal_bridge.register_fal_skill(tools, {"enabled": True})
    names = {t.name for t in tools}
    assert names == {
        "generate_flux_image",
        "generate_kling_video",
        "execute_comfy_workflow",
        "edit_visual_asset",
    }


def test_fal_queue_urls_from_submit_uses_api_urls() -> None:
    status, response = fal_bridge._fal_queue_urls_from_submit(
        {
            "status_url": "https://queue.fal.run/fal-ai/flux/requests/abc/status",
            "response_url": "https://queue.fal.run/fal-ai/flux/requests/abc",
        },
        "fal-ai/flux/dev",
        "abc",
    )
    assert status.endswith("/abc/status")
    assert response.endswith("/abc")


def test_fal_queue_urls_fallback_strips_dev_subpath() -> None:
    status, response = fal_bridge._fal_queue_urls_from_submit(
        {},
        "fal-ai/flux/dev",
        "rid-1",
    )
    assert status == "https://queue.fal.run/fal-ai/flux/requests/rid-1/status"
    assert response == "https://queue.fal.run/fal-ai/flux/requests/rid-1"


def test_extract_media_url_image() -> None:
    url = fal_bridge._extract_media_url(
        {"response": {"images": [{"url": "https://cdn.example/x.png"}]}},
        "image",
    )
    assert url == "https://cdn.example/x.png"


async def _fake_fal_generate(**kwargs: Any) -> str:
    return json.dumps({
        "ok": True,
        "success": True,
        "media_url": "https://cdn.example/x.png",
        "file_path": "/tmp/x.png",
        "latency_sec": 1.0,
        "cost_usd": 0.025,
    })


def test_generate_flux_image_impl_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fal_bridge, "_fal_generate_async", _fake_fal_generate)
    out = json.loads(
        fal_bridge._generate_flux_image_impl("studio orb", duckclaw_db=_FakeDb())
    )
    assert out.get("ok") is True
    assert out.get("success") is True


def test_denoise_to_strength_mapping() -> None:
    assert fal_bridge._denoise_to_strength(0.35) == pytest.approx(0.7275)
    assert fal_bridge._denoise_to_strength(0.55) == pytest.approx(0.8575)
    assert fal_bridge._denoise_to_strength(0.75) == pytest.approx(0.98)


def test_local_image_to_data_uri_jpeg(tmp_path: Path) -> None:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
    uri = fal_bridge._local_image_to_data_uri(img)
    assert uri.startswith("data:image/jpeg;base64,")


def test_is_kontext_edit_endpoint() -> None:
    assert fal_bridge._is_kontext_edit_endpoint("fal-ai/flux-pro/kontext") is True
    assert fal_bridge._is_kontext_edit_endpoint("fal-ai/flux-kontext/dev") is True
    assert fal_bridge._is_kontext_edit_endpoint("fal-ai/flux/dev/image-to-image") is False


def test_build_fal_edit_request_body_kontext() -> None:
    body = fal_bridge._build_fal_edit_request_body(
        endpoint="fal-ai/flux-pro/kontext",
        image_uri="data:image/jpeg;base64,abc",
        edit_prompt="cambia la ropa a amarillo",
        denoise=0.55,
        fal_config={},
    )
    assert "strength" not in body
    assert body["guidance_scale"] == pytest.approx(3.5)
    assert "cambia la ropa a amarillo" in body["prompt"]
    assert "Keep the same person" in body["prompt"]


def test_build_fal_edit_request_body_legacy_img2img() -> None:
    body = fal_bridge._build_fal_edit_request_body(
        endpoint="fal-ai/flux/dev/image-to-image",
        image_uri="data:image/jpeg;base64,abc",
        edit_prompt="cambia el fondo",
        denoise=0.55,
        fal_config={},
    )
    assert body.get("strength") == pytest.approx(0.8575)
    assert body["prompt"] == "cambia el fondo"
    assert "guidance_scale" not in body


def test_fal_edit_visual_asset_impl_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import vaults

    monkeypatch.setattr(vaults, "db_root", lambda: tmp_path / "db")
    monkeypatch.setattr(
        fal_bridge,
        "_state_delta_base",
        lambda: {"tenant_id": "tenant_x", "user_id": "u1", "target_db_path": ""},
    )
    inbound = vaults.user_vault_dir("tenant_x") / "inbound"
    inbound.mkdir(parents=True)
    src = inbound / "src.jpg"
    src.write_bytes(b"\xff\xd8" + b"\x00" * 40)

    captured: dict[str, Any] = {}

    async def _capture_fal_generate(**kwargs: Any) -> str:
        captured.update(kwargs)
        return json.dumps({"ok": True, "success": True, "file_path": "/tmp/edited.jpg"})

    monkeypatch.setattr(fal_bridge, "_fal_generate_async", _capture_fal_generate)
    out = json.loads(
        fal_bridge._fal_edit_visual_asset_impl(
            str(src),
            "cambia el fondo a playa",
            duckclaw_db=_FakeDb(),
        )
    )
    assert out.get("ok") is True
    assert captured.get("persist_operation") == "fal_kontext_edit"
    assert captured.get("endpoint") == "fal-ai/flux-pro/kontext"
    assert captured.get("source_image_path") == str(src.resolve())
    body = captured.get("body") or {}
    assert "cambia el fondo a playa" in str(body.get("prompt", ""))
    assert "strength" not in body
    assert str(body.get("image_url", "")).startswith("data:image/jpeg;base64,")


def test_edit_fallback_to_comfy_when_fal_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import vaults

    monkeypatch.setattr(vaults, "db_root", lambda: tmp_path / "db")
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    monkeypatch.setattr(
        fal_bridge,
        "_state_delta_base",
        lambda: {"tenant_id": "tenant_x", "user_id": "u1", "target_db_path": ""},
    )
    inbound = vaults.user_vault_dir("tenant_x") / "inbound"
    inbound.mkdir(parents=True)
    src = inbound / "src.jpg"
    src.write_bytes(b"\xff\xd8" + b"\x00" * 40)

    monkeypatch.setattr(
        fal_bridge,
        "_fal_edit_visual_asset_impl",
        lambda *a, **k: json.dumps({"ok": False, "error": "fal timeout"}),
    )
    from duckclaw.forge.skills import comfyui_bridge

    monkeypatch.setattr(
        comfyui_bridge,
        "_edit_visual_asset_impl",
        lambda *a, **k: json.dumps({"ok": True, "file_path": "/tmp/comfy.jpg"}),
    )

    out = json.loads(
        fal_bridge._edit_visual_asset_with_fallback(
            str(src),
            "quita lentes",
            comfyui_config={"enabled": True},
            duckclaw_db=_FakeDb(),
        )
    )
    assert out.get("ok") is True
    assert out.get("file_path") == "/tmp/comfy.jpg"
