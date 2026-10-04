"""Extension python_requirements: resolved from the fly manifest and installed after uv sync."""

from __future__ import annotations

from pathlib import Path


def test_requirements_resolve_relative_to_manifest(tmp_path: Path, monkeypatch) -> None:
    from duckclaw.extensions import python_requirements as pr

    ext = tmp_path / "ext" / "workers"
    ext.mkdir(parents=True)
    (ext / "requirements.txt").write_text("somepkg>=1\n", encoding="utf-8")
    manifest = ext / "fly_extension.yaml"
    manifest.write_text("python_requirements:\n  - requirements.txt\n  - missing.txt\n", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_FLY_MANIFEST", str(manifest))

    assert pr.extension_requirement_files() == [(ext / "requirements.txt").resolve()]

    calls: list[list[str]] = []

    class _Proc:
        returncode = 0

    monkeypatch.setattr(pr.subprocess, "run", lambda cmd, **_kw: calls.append(cmd) or _Proc())
    assert pr.install_extension_python_requirements(repo_root=tmp_path, print_fn=lambda _m: None)
    assert calls == [["uv", "pip", "install", "--quiet", "-r", str((ext / "requirements.txt").resolve())]]


def test_no_manifest_installs_nothing(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.extensions import python_requirements as pr

    monkeypatch.delenv("DUCKCLAW_FLY_MANIFEST", raising=False)
    assert pr.extension_requirement_files() == []
    assert pr.install_extension_python_requirements(repo_root=tmp_path, print_fn=lambda _m: None)
