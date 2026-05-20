"""Tests unitarios del bridge ComfyUI (sin servidor real)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from duckclaw.forge.skills.comfyui_bridge import (
    apply_aspect_ratio,
    apply_checkpoint,
    _poll_history_until_done,
    _queue_prompt_ids,
    inject_clip_prompts,
    inject_ksampler_denoise,
    inject_load_image,
    load_workflow_template,
    read_artifact_image_as_b64,
    register_comfyui_skill,
    reset_comfyui_runtime,
    validate_source_image_path,
)


def test_load_workflow_template_comfy_default() -> None:
    wf, meta = load_workflow_template("comfy_default")
    assert isinstance(wf, dict)
    assert "6" in wf
    assert wf["6"]["class_type"] == "CLIPTextEncode"
    assert isinstance(meta.get("aspect_presets"), dict)


def test_inject_clip_prompts_uses_meta() -> None:
    wf, meta = load_workflow_template("comfy_default")
    out = inject_clip_prompts(wf, "sunset over mountains", "blurry", meta)
    assert out["6"]["inputs"]["text"] == "sunset over mountains"
    assert out["7"]["inputs"]["text"] == "blurry"


def test_apply_aspect_ratio_16_9() -> None:
    wf, meta = load_workflow_template("comfy_default")
    out = apply_aspect_ratio(wf, "16:9", meta)
    assert out["5"]["inputs"]["width"] == 1344
    assert out["5"]["inputs"]["height"] == 768


def test_apply_checkpoint_no_models(monkeypatch: pytest.MonkeyPatch) -> None:
    wf, meta = load_workflow_template("comfy_default")

    def _empty(_url: str) -> list[str]:
        return []

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge.list_comfy_checkpoints",
        _empty,
    )
    _, err = apply_checkpoint(wf, meta, "http://127.0.0.1:8188")
    assert err is not None
    assert "No hay checkpoints" in err


def test_poll_history_until_done(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _fake_finished(_pid: str, _url: str) -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge._history_prompt_finished",
        _fake_finished,
    )
    monkeypatch.setattr("duckclaw.forge.skills.comfyui_bridge.time.sleep", lambda _s: None)
    import time

    _poll_history_until_done("pid-1", "http://127.0.0.1:8188", time.monotonic() + 10)
    assert calls["n"] == 2


def test_wait_for_completion_ws_fail_polls_history(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeWs:
        def recv(self, timeout=None):
            raise ConnectionError("keepalive ping timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_connect(*_a, **_k):
        return _FakeWs()

    monkeypatch.setattr(
        "websockets.sync.client.connect",
        _fake_connect,
    )
    flags = iter([False, True])

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge._history_prompt_finished",
        lambda *_a, **_k: next(flags, True),
    )
    from duckclaw.forge.skills.comfyui_bridge import wait_for_completion

    wait_for_completion("pid-1", "client-1", "http://127.0.0.1:8188", timeout_sec=30)


def test_apply_checkpoint_picks_first_available(monkeypatch: pytest.MonkeyPatch) -> None:
    wf, meta = load_workflow_template("comfy_default")

    def _one(_url: str) -> list[str]:
        return ["sd_xl.safetensors"]

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge.list_comfy_checkpoints",
        _one,
    )
    out, err = apply_checkpoint(wf, meta, "http://127.0.0.1:8188")
    assert err is None
    assert out["4"]["inputs"]["ckpt_name"] == "sd_xl.safetensors"


def test_register_comfyui_skill_disabled() -> None:
    tools: list = []
    register_comfyui_skill(tools, {"enabled": False})
    assert tools == []


def test_register_comfyui_skill_adds_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    tools: list = []
    register_comfyui_skill(tools, {"enabled": True})
    names = [getattr(t, "name", None) for t in tools]
    assert "generate_visual_asset" in names
    assert "edit_visual_asset" in names


def test_read_artifact_image_as_b64_rejects_outside_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import vaults

    monkeypatch.setattr(vaults, "db_root", lambda: tmp_path / "db")
    tenant_dir = vaults.user_vault_dir("tenant_a") / "artifacts"
    tenant_dir.mkdir(parents=True)
    good = tenant_dir / "img.png"
    good.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    outside = tmp_path / "evil.png"
    outside.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    b64 = read_artifact_image_as_b64(str(good), "tenant_a")
    assert len(b64) > 32
    assert read_artifact_image_as_b64(str(outside), "tenant_a") == ""


def test_inject_load_image_and_denoise() -> None:
    wf, meta = load_workflow_template("comfy_img2img_edit")
    wf2 = inject_load_image(wf, "uploaded.png", meta)
    assert wf2["10"]["inputs"]["image"] == "uploaded.png"
    wf3 = inject_ksampler_denoise(wf2, 0.42, meta)
    assert wf3["3"]["inputs"]["denoise"] == 0.42


def test_validate_source_inbound_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw import vaults

    monkeypatch.setattr(vaults, "db_root", lambda: tmp_path / "db")
    inbound = vaults.user_vault_dir("tenant_x") / "inbound"
    inbound.mkdir(parents=True)
    img = inbound / "src.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 40)
    resolved = validate_source_image_path(str(img), "tenant_x")
    assert resolved == img.resolve()


def test_queue_prompt_ids_parses_running_and_pending() -> None:
    payload = {
        "queue_running": [[1, "run-abc", {}, {}]],
        "queue_pending": [[2, "pend-xyz", {}, {}]],
    }
    assert _queue_prompt_ids(payload) == ["run-abc", "pend-xyz"]


def test_reset_comfyui_runtime_calls_interrupt_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def _fake_http(method: str, url: str, body: dict | None = None, **kwargs: object) -> object:
        calls.append((method, url, body))
        if method == "GET" and url.endswith("/queue"):
            return {"queue_pending": [[1, "p1", {}, {}]], "queue_running": []}
        return {}

    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    monkeypatch.setattr("duckclaw.forge.skills.comfyui_bridge._http_json", _fake_http)
    out = reset_comfyui_runtime()
    assert out["interrupt"] is True
    assert out["deleted_pending"] == 1
    assert any(c[0] == "POST" and c[1].endswith("/interrupt") for c in calls)


def test_generate_visual_asset_empty_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.comfyui_bridge import _generate_visual_asset_impl

    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    raw = _generate_visual_asset_impl("", duckclaw_db=None)
    data = json.loads(raw)
    assert data.get("ok") is False


def test_state_delta_base_uses_gateway_hub_not_worker_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.comfyui_bridge import _state_delta_base
    from duckclaw.forge.skills.quant_tool_context import (
        set_quant_tool_db_path,
        set_quant_tool_tenant_id,
        set_quant_tool_user_id,
    )

    hub = "/tmp/finanzdb1.duckdb"
    worker_vault = "/tmp/quant_traderdb1.duckdb"
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: hub,
    )
    set_quant_tool_db_path(worker_vault)
    set_quant_tool_tenant_id("Cuantitativo")
    set_quant_tool_user_id("1726618406")
    base = _state_delta_base()
    assert base["target_db_path"] == hub
    assert base["target_db_path"] != worker_vault
    assert base["tenant_id"] == "Cuantitativo"
    assert base["user_id"] == "1726618406"
