"""Manifest parsea bloque comfyui."""

from __future__ import annotations

from duckclaw.workers.manifest import load_manifest


def test_load_manifest_default_has_comfyui_config() -> None:
    spec = load_manifest("default")
    cfg = getattr(spec, "comfyui_config", None)
    assert isinstance(cfg, dict)
    assert cfg.get("enabled") is True
    assert cfg.get("template") == "comfy_default"
    assert cfg.get("edit_template") == "comfy_img2img_edit"
