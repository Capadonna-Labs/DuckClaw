from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_list_disk_roots_and_folder_and_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "allowed"
    nested = root / "pkg"
    nested.mkdir(parents=True)
    sample = nested / "hello.py"
    sample.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(root))
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", raising=False)

    from duckclaw.forge.skills.disk_knowledge_bridge import (
        list_disk_folder,
        list_disk_roots,
        read_disk_text,
        register_disk_knowledge_tools,
    )

    roots = json.loads(list_disk_roots())
    assert roots["ok"] is True
    assert roots["lane"] == "disk"
    assert any(r["path"] == str(root.resolve()) for r in roots["roots"])

    top = json.loads(list_disk_folder(path="", include_files=False))
    assert top["ok"] is True
    assert top.get("roots_mode") is True

    listing = json.loads(list_disk_folder(path=str(root), include_files=True))
    assert listing["ok"] is True
    names = {e["name"] for e in listing["entries"]}
    assert "pkg" in names

    nested_listing = json.loads(
        list_disk_folder(path=str(nested), include_files=True)
    )
    assert any(e["name"] == "hello.py" for e in nested_listing["entries"])

    body = json.loads(read_disk_text(path=str(sample)))
    assert body["ok"] is True
    assert "print('ok')" in body["content"]

    tools: list = []
    register_disk_knowledge_tools(tools)
    assert {t.name for t in tools} == {
        "list_disk_roots",
        "list_disk_folder",
        "read_disk_text",
    }


def test_read_disk_text_rejects_outside_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(root))
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", raising=False)

    from duckclaw.forge.skills.disk_knowledge_bridge import read_disk_text

    err = json.loads(read_disk_text(path=str(outside)))
    assert err["ok"] is False
    assert "error" in err


def test_knowledge_tool_copy_contracts_mention_disk_tools() -> None:
    from duckclaw.forge.skills.knowledge_tool_copy import (
        EXTRACT_DOCUMENT_TEXT_DESCRIPTION,
        GET_PROJECT_CONTEXT_DESCRIPTION,
        LIST_DISK_FOLDER_DESCRIPTION,
        READ_DISK_TEXT_DESCRIPTION,
        SEARCH_PROJECT_KNOWLEDGE_DESCRIPTION,
    )

    assert "list_disk_folder" in GET_PROJECT_CONTEXT_DESCRIPTION
    assert "read_disk_text" in GET_PROJECT_CONTEXT_DESCRIPTION
    assert "[Disco" in LIST_DISK_FOLDER_DESCRIPTION
    assert "[RAG" in SEARCH_PROJECT_KNOWLEDGE_DESCRIPTION
    assert "read_disk_text" in EXTRACT_DOCUMENT_TEXT_DESCRIPTION
    assert "extract_document_text" in READ_DISK_TEXT_DESCRIPTION
