"""Tests for vault mirror + kiwix offline helpers."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_list_zim_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.vault_mirror import list_zim_files

    zim_dir = tmp_path / "zim"
    zim_dir.mkdir()
    (zim_dir / "wiki.zim").write_bytes(b"zim")
    (zim_dir / "note.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_KIWIX_ZIM_DIR", str(zim_dir))
    files = list_zim_files()
    assert len(files) == 1
    assert files[0].name == "wiki.zim"


def test_run_vault_mirror_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.vault_mirror import run_vault_mirror

    src = tmp_path / "src"
    dst = tmp_path / "mirror"
    src.mkdir()
    (src / "doc.md").write_text("hola", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "a.txt").write_text("a", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_VAULT_SOURCE_DIR", str(src))
    monkeypatch.setenv("DUCKCLAW_VAULT_MIRROR_DIR", str(dst))
    result = run_vault_mirror(delete=False, dry_run=False)
    assert result.ok is True
    assert (dst / "doc.md").read_text(encoding="utf-8") == "hola"
    assert (dst / "sub" / "a.txt").read_text(encoding="utf-8") == "a"


def test_knowledge_allowed_roots_prepends_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots

    gdrive = tmp_path / "gdrive"
    mirror = tmp_path / "mirror"
    gdrive.mkdir()
    mirror.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(gdrive))
    monkeypatch.setenv("DUCKCLAW_VAULT_MIRROR_DIR", str(mirror))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)
    roots = knowledge_allowed_roots()
    assert roots[0] == mirror.resolve()
    assert gdrive.resolve() in roots


def test_kiwix_tool_none_without_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.kiwix_bridge import kiwix_search_tool

    monkeypatch.delenv("DUCKCLAW_KIWIX_ZIM_DIR", raising=False)
    assert kiwix_search_tool({"kiwix_enabled": True}) is None


def test_kiwix_tool_registers_with_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckclaw.forge.skills import kiwix_bridge

    zim_dir = tmp_path / "zim"
    zim_dir.mkdir()
    monkeypatch.setenv("DUCKCLAW_KIWIX_ZIM_DIR", str(zim_dir))
    monkeypatch.setattr(kiwix_bridge, "kiwix_cli_available", lambda: True)
    tool = kiwix_bridge.kiwix_search_tool({"kiwix_enabled": True})
    assert tool is not None
    assert tool.name == "kiwix_search"
    out = tool.invoke({"query": "test"})
    assert "No hay archivos .zim" in out or "library.kiwix.org" in out


def test_html_to_text_strips_tags() -> None:
    from duckclaw.forge.skills.kiwix_bridge import _html_to_text

    out = _html_to_text("<html><body><h1>Hola</h1><p>Mundo &amp; paz</p></body></html>")
    assert "Hola" in out
    assert "Mundo & paz" in out
    assert "<" not in out


def test_register_kiwix_tools_includes_read_when_libzim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckclaw.forge.skills import kiwix_bridge

    zim_dir = tmp_path / "zim"
    zim_dir.mkdir()
    monkeypatch.setenv("DUCKCLAW_KIWIX_ZIM_DIR", str(zim_dir))
    monkeypatch.setattr(kiwix_bridge, "kiwix_cli_available", lambda: True)
    monkeypatch.setattr(kiwix_bridge, "libzim_available", lambda: True)
    tools: list = []
    kiwix_bridge.register_kiwix_tools(tools, {"kiwix_enabled": True})
    names = [getattr(t, "name", "") for t in tools]
    assert "kiwix_search" in names
    assert "kiwix_read" in names
