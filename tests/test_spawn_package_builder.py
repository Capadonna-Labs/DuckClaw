"""Spawn package zip builder tests."""

from __future__ import annotations

import io
import json
import zipfile

from duckclaw.spawn_package_builder import build_spawn_readme


def test_spawn_readme_mentions_db_import() -> None:
    text = build_spawn_readme("demo-worker")
    assert "Importar worker" in text or "spawn-package/import" in text
    assert "system_prompt.md" in text


def test_extract_spawn_package_roundtrip() -> None:
    from duckclaw.spawn_package_extract import extract_spawn_package

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("demo-spawn-package/manifest.yaml", "id: demo\nskills: []\n")
        zf.writestr("demo-spawn-package/soul.md", "hello")
    files = extract_spawn_package(buf.getvalue())
    assert "manifest.yaml" in files
    assert files["manifest.yaml"].startswith("id:")


def test_analyze_spawn_package_high_risk() -> None:
    from duckclaw.spawn_risk_policy import analyze_spawn_package

    manifest = {
        "id": "risky",
        "skills": ["admin_sql"],
        "tool_surface": {"expose_privileged_mutation_tools": ["admin_sql"]},
    }
    files = {"manifest.yaml": "id: risky\n", "system_prompt.md": "x"}
    analysis = analyze_spawn_package(manifest, files, available_tools=["read_sql"])
    assert analysis.import_blocked_until_confirm is True
    assert any("admin_sql" in f for f in analysis.high_risk_findings)
