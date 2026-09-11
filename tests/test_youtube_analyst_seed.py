"""Contract for forge/seed/youtube-analyst template."""

from __future__ import annotations

from pathlib import Path

import yaml

from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id
from duckclaw.forge import WORKERS_TEMPLATES_DIR
from duckclaw.workers.manifest import build_spec_from_manifest


def _youtube_analyst_dir() -> Path:
    path = WORKERS_TEMPLATES_DIR / "youtube-analyst"
    assert path.is_dir(), f"missing seed template: {path}"
    return path


def test_youtube_analyst_seed_manifest_contract() -> None:
    wdir = _youtube_analyst_dir()
    manifest_path = wdir / "manifest.yaml"
    assert manifest_path.is_file()
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    assert data.get("id") == "youtube-analyst"
    assert sanitize_catalog_worker_id(str(data["id"])) == "youtube-analyst"
    assert str(data.get("display_name") or "").strip() == "YouTube Analyst"
    assert data.get("read_only") is True

    skills = data.get("skills") or []
    assert any(
        (isinstance(s, str) and s.replace("-", "_") == "youtube_transcript")
        or (isinstance(s, dict) and "youtube_transcript" in s)
        for s in skills
    )

    yt_cfg = next(
        (s["youtube_transcript"] for s in skills if isinstance(s, dict) and "youtube_transcript" in s),
        None,
    )
    assert isinstance(yt_cfg, dict) and yt_cfg, "youtube_transcript requires non-empty config"

    assert (wdir / "soul.md").is_file()
    assert (wdir / "system_prompt.md").is_file()

    spec = build_spec_from_manifest(data, "youtube-analyst", wdir)
    assert spec.read_only is True
    assert "youtube_transcript" in spec.skills_list
    assert isinstance(spec.skill_configs.get("youtube_transcript"), dict)
    assert spec.skill_configs["youtube_transcript"].get("response_limit") == 15000
