"""Tests for admin knowledge folder browse (server-side picker)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_browse_knowledge_roots_lists_allowed_directories(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = tmp_path / "docs"
    allowed.mkdir()
    (allowed / "notes").mkdir()
    (allowed / "readme.md").write_text("# hi", encoding="utf-8")
    (allowed / ".hidden").mkdir()

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(allowed))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)

    response = gateway_admin_client.get(
        "/api/v1/admin/knowledge/browse",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["roots_mode"] is True
    assert payload["path"] == ""
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["name"] == "docs"
    assert payload["entries"][0]["selectable"] is True


def test_browse_knowledge_subdirectory_hides_dot_dirs(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = tmp_path / "vault"
    sub = allowed / "projects"
    sub.mkdir(parents=True)
    (sub / "alpha").mkdir()
    (sub / ".git").mkdir()

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(allowed))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)

    response = gateway_admin_client.get(
        "/api/v1/admin/knowledge/browse",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"path": str(sub)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["roots_mode"] is False
    assert payload["path"] == str(sub.resolve())
    names = [entry["name"] for entry in payload["entries"]]
    assert names == ["alpha"]
    assert payload["parent_path"] == str(allowed.resolve())


def test_browse_knowledge_rejects_path_outside_allowed_roots(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(allowed))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)

    response = gateway_admin_client.get(
        "/api/v1/admin/knowledge/browse",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"path": str(outside)},
    )
    assert response.status_code == 400
