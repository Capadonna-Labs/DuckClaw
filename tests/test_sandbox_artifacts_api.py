"""Tests sandbox artifacts registry + admin gateway API."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GW_DIR = _REPO_ROOT / "services" / "api-gateway"
if str(_GW_DIR) not in sys.path:
    sys.path.insert(0, str(_GW_DIR))


def _mock_playground_team(*, authorized: bool = True) -> dict:
    return {
        "workers": ["default"],
        "authorized": authorized,
        "team_chat_id": "admin-playground",
        "telegram_user_id": "test-owner",
        "tenant_id": "default",
        "whitelist_role": "owner",
        "team_source": "chat",
        "team_hint": "mock",
    }


def _seed_run(
    sandbox_root: Path,
    *,
    chat_id: str = "admin-playground",
    run_id: str | None = None,
    artifacts: list[dict] | None = None,
    expires_at: float | None = None,
) -> tuple[str, list[dict]]:
    from duckclaw.sandbox_artifacts import sanitize_chat_to_session_id, write_run_manifest

    rid = run_id or uuid.uuid4().hex
    session_id = sanitize_chat_to_session_id(chat_id)
    run_dir = sandbox_root / session_id / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    seeded: list[dict] = []
    for spec in artifacts or []:
        name = spec["filename"]
        body = spec.get("content", b"")
        if isinstance(body, str):
            body = body.encode("utf-8")
        (run_dir / name).write_bytes(body)
        entry = {
            "artifact_id": spec.get("artifact_id") or str(uuid.uuid4()),
            "filename": name,
            "relative_path": name,
            "mime": spec.get("mime", "application/octet-stream"),
            "byte_size": len(body),
            "previewable": spec.get("previewable", True),
        }
        seeded.append(entry)

    write_run_manifest(
        chat_id=chat_id,
        run_id=rid,
        artifacts=seeded,
        expires_at=expires_at,
        base=sandbox_root,
    )
    return rid, seeded


@pytest.fixture
def sandbox_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    monkeypatch.setenv("DUCKCLAW_SANDBOX_ARTIFACTS_ROOT", str(root))
    return root


def test_sandbox_path_traversal_blocked(sandbox_root: Path) -> None:
    from duckclaw.sandbox_artifacts import PathTraversalError, find_artifact, write_run_manifest

    rid = uuid.uuid4().hex
    session = "admin_playground"
    run_dir = sandbox_root / session / rid
    run_dir.mkdir(parents=True)
    artifact_id = str(uuid.uuid4())
    write_run_manifest(
        chat_id="admin-playground",
        run_id=rid,
        artifacts=[
            {
                "artifact_id": artifact_id,
                "filename": "evil.txt",
                "relative_path": "../outside.txt",
                "mime": "text/plain",
                "byte_size": 0,
                "previewable": True,
            }
        ],
        base=sandbox_root,
    )
    with pytest.raises(PathTraversalError):
        find_artifact("admin-playground", artifact_id, base=sandbox_root)


def test_purge_expired_runs(sandbox_root: Path) -> None:
    from duckclaw.sandbox_artifacts import purge_expired_runs

    expired_id, _ = _seed_run(
        sandbox_root,
        run_id=uuid.uuid4().hex,
        artifacts=[{"filename": "old.md", "content": "x", "mime": "text/markdown"}],
        expires_at=time.time() - 10,
    )
    fresh_id, _ = _seed_run(
        sandbox_root,
        run_id=uuid.uuid4().hex,
        artifacts=[{"filename": "new.md", "content": "y", "mime": "text/markdown"}],
        expires_at=time.time() + 3600,
    )

    result = purge_expired_runs(base=sandbox_root)
    assert result["purged"] == 1
    assert expired_id in result["run_ids"]
    assert not (sandbox_root / "admin_playground" / expired_id).exists()
    assert (sandbox_root / "admin_playground" / fresh_id).exists()


def test_list_runs_for_chat(sandbox_root: Path) -> None:
    from duckclaw.sandbox_artifacts import list_runs_for_chat

    _seed_run(
        sandbox_root,
        artifacts=[{"filename": "a.md", "content": "# A", "mime": "text/markdown"}],
    )
    runs = list_runs_for_chat("admin-playground", limit=10, base=sandbox_root)
    assert len(runs) == 1
    assert runs[0]["artifact_count"] == 1


def test_preview_markdown_content(sandbox_root: Path) -> None:
    from duckclaw.sandbox_artifacts import find_artifact, preview_content

    _, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "# Hola", "mime": "text/markdown"}],
    )
    _, entry, path = find_artifact("admin-playground", entries[0]["artifact_id"], base=sandbox_root)
    result = preview_content(path, mime=entry["mime"], filename=entry["filename"])
    assert result.kind == "json"
    assert result.payload["preview_kind"] == "markdown"
    assert "Hola" in result.payload["content"]


def test_preview_png_binary(sandbox_root: Path) -> None:
    from duckclaw.sandbox_artifacts import find_artifact, preview_content

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    _, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "plot.png", "content": png, "mime": "image/png"}],
    )
    _, entry, path = find_artifact("admin-playground", entries[0]["artifact_id"], base=sandbox_root)
    result = preview_content(path, mime=entry["mime"], filename=entry["filename"])
    assert result.kind == "binary"
    assert result.mime == "image/png"
    assert result.data.startswith(b"\x89PNG")


def test_api_list_runs(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )
    _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "# test", "mime": "text/markdown"}],
    )

    r = gateway_admin_client.get(
        "/api/v1/admin/sandbox/artifacts/runs",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 1
    assert data["runs"][0]["artifact_count"] == 1


def test_api_get_run_detail(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )
    run_id, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "# detalle", "mime": "text/markdown"}],
    )

    r = gateway_admin_client.get(
        f"/api/v1/admin/sandbox/artifacts/runs/{run_id}",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    run = r.json()["run"]
    assert run["run_id"] == run_id
    assert len(run["artifacts"]) == 1
    assert run["artifacts"][0]["artifact_id"] == entries[0]["artifact_id"]


def test_api_preview_md(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )
    _run_id, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "# Preview API", "mime": "text/markdown"}],
    )
    artifact_id = entries[0]["artifact_id"]

    r = gateway_admin_client.get(
        f"/api/v1/admin/sandbox/artifacts/{artifact_id}/preview",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_kind"] == "markdown"
    assert "Preview API" in body["content"]


def test_api_preview_png_stream(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    _run_id, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "plot.png", "content": png, "mime": "image/png"}],
    )
    artifact_id = entries[0]["artifact_id"]

    r = gateway_admin_client.get(
        f"/api/v1/admin/sandbox/artifacts/{artifact_id}/preview",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content.startswith(b"\x89PNG")


def test_api_download(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )
    _run_id, entries = _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "download-me", "mime": "text/markdown"}],
    )
    artifact_id = entries[0]["artifact_id"]

    r = gateway_admin_client.get(
        f"/api/v1/admin/sandbox/artifacts/{artifact_id}/download",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    assert b"download-me" in r.content


def test_api_cleanup(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired_id, _ = _seed_run(
        sandbox_root,
        run_id=uuid.uuid4().hex,
        artifacts=[{"filename": "old.md", "content": "x", "mime": "text/markdown"}],
        expires_at=time.time() - 5,
    )

    r = gateway_admin_client.post(
        "/api/v1/admin/sandbox/artifacts/cleanup",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["purged"] >= 1
    assert not (sandbox_root / "admin_playground" / expired_id).exists()


def test_api_unauthorized_chat(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(authorized=False),
    )
    _seed_run(
        sandbox_root,
        artifacts=[{"filename": "out.md", "content": "nope", "mime": "text/markdown"}],
    )

    r = gateway_admin_client.get(
        "/api/v1/admin/sandbox/artifacts/runs",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 403


def test_api_preview_docx_when_markitdown_available(
    gateway_admin_client: TestClient,
    sandbox_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.document_toolbox.extract import markitdown_available

    if not markitdown_available():
        pytest.skip("MarkItDown no instalado")

    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(),
    )

    docx_path = _REPO_ROOT / "packages" / "shared" / "src" / "duckclaw" / "seeds" / "document_templates"
    candidates = list(docx_path.glob("*.docx"))
    if not candidates:
        pytest.skip("sin plantilla docx de seed")

    content = candidates[0].read_bytes()
    _run_id, entries = _seed_run(
        sandbox_root,
        artifacts=[
            {
                "filename": "report.docx",
                "content": content,
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ],
    )
    artifact_id = entries[0]["artifact_id"]

    r = gateway_admin_client.get(
        f"/api/v1/admin/sandbox/artifacts/{artifact_id}/preview",
        params={"chat_id": "admin-playground"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_kind"] == "text"
    assert isinstance(body.get("content"), str)
    assert len(body["content"]) > 0
