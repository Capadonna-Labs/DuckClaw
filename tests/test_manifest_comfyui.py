"""Manifest parsea bloque comfyui cuando está declarado."""

from __future__ import annotations

from duckclaw.workers.manifest import build_spec_from_manifest, load_manifest


def test_load_manifest_default_is_scaffold_without_comfyui(catalog_db) -> None:
    spec = load_manifest("default", db=catalog_db, tenant_id="default")
    assert spec is not None
    assert "comfyui" not in (spec.skill_configs or {})


def test_build_spec_parses_comfyui_skill_config() -> None:
    from pathlib import Path

    spec = build_spec_from_manifest(
        {
            "name": "Comfy demo",
            "skills": [
                {
                    "comfyui": {
                        "enabled": True,
                        "template": "comfy_default",
                        "edit_template": "comfy_img2img_edit",
                    }
                }
            ],
        },
        "comfy_demo",
        Path(__file__).resolve().parents[1],
    )
    cfg = spec.skill_configs.get("comfyui")
    assert isinstance(cfg, dict)
    assert cfg.get("enabled") is True
    assert cfg.get("template") == "comfy_default"
    assert cfg.get("edit_template") == "comfy_img2img_edit"
