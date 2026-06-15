"""Manifest parsea bloque fal."""

from __future__ import annotations

from pathlib import Path

import yaml

from duckclaw.workers.manifest import build_spec_from_manifest


def test_load_manifest_fal_from_skills_block(tmp_path: Path) -> None:
    wdir = tmp_path / "templates" / "workers" / "test-fal"
    wdir.mkdir(parents=True)
    manifest = {
        "name": "TestFal",
        "id": "test_fal",
        "skills": [{"fal": {"enabled": True, "default_image_endpoint": "fal-ai/flux/dev"}}],
    }
    (wdir / "manifest.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
    spec = build_spec_from_manifest(manifest, "test-fal", wdir)
    cfg = spec.skill_configs.get("fal")
    assert isinstance(cfg, dict)
    assert cfg.get("enabled") is True
    assert cfg.get("default_image_endpoint") == "fal-ai/flux/dev"
