"""Unit tests: sandbox artifact registry, manifest, TTL purge, path guards."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from duckclaw.sandbox_artifacts import (
    MANIFEST_NAME,
    chat_session_dir,
    get_run,
    list_runs,
    preview_artifact,
    purge_expired_runs,
    read_artifact_bytes,
    register_run_artifacts,
    resolve_artifact,
    sandbox_artifact_ttl_s,
    sandbox_output_root,
    sanitize_chat_to_session_id,
)


def test_sanitize_chat_to_session_id_matches_novnc_registry() -> None:
    from duckclaw.graphs.novnc_registry import sanitize_chat_to_session_id as novnc_sanitize

    samples = ["playground-abc", "chat/with\\slashes", "", "   ", "x" * 80]
    for sample in samples:
        assert sanitize_chat_to_session_id(sample) == novnc_sanitize(sample)


def test_paths_under_cwd_output_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    chat_id = "playground-demo"
    session = chat_session_dir(chat_id)
    assert session == tmp_path / "output" / "sandbox" / "playground_demo"
    assert sandbox_output_root() == tmp_path / "output" / "sandbox"


def test_register_run_artifacts_writes_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKCLAW_SANDBOX_ARTIFACT_TTL_S", "3600")
    src = tmp_path / "src"
    src.mkdir()
    chart = src / "chart.png"
    chart.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 20)
    notes = src / "out.md"
    notes.write_text("# Hola\n", encoding="utf-8")

    manifest = register_run_artifacts(
        "playground-1",
        "tenant-a",
        "worker-x",
        "run-abc",
        0,
        [chart, notes],
    )
    run_dir = chat_session_dir("playground-1") / "run-abc"
    assert (run_dir / MANIFEST_NAME).is_file()
    assert manifest["run_id"] == "run-abc"
    assert manifest["chat_session_id"] == "playground_1"
    assert manifest["tenant_id"] == "tenant-a"
    assert manifest["worker_id"] == "worker-x"
    assert len(manifest["artifacts"]) == 2
    assert (run_dir / "chart.png").is_file()
    assert (run_dir / "out.md").is_file()
    assert manifest["expires_at"] > manifest["created_at"]
    assert int(manifest["expires_at"] - manifest["created_at"]) == sandbox_artifact_ttl_s()


def test_list_runs_and_get_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f1 = src / "a.txt"
    f1.write_text("one", encoding="utf-8")
    f2 = src / "b.txt"
    f2.write_text("two", encoding="utf-8")
    register_run_artifacts("chat-a", "default", "w", "run-old", 0, [f1])
    time.sleep(0.01)
    register_run_artifacts("chat-a", "default", "w", "run-new", 0, [f2])

    runs = list_runs("chat-a", limit=10)
    assert [r["run_id"] for r in runs] == ["run-new", "run-old"]

    detail = get_run("run-new", "chat-a")
    assert detail is not None
    assert detail["run_id"] == "run-new"
    assert get_run("missing", "chat-a") is None


def test_resolve_read_and_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    md = src / "note.md"
    md.write_text("**bold**", encoding="utf-8")
    manifest = register_run_artifacts("chat-prev", "default", "w", "run1", 0, [md])
    aid = manifest["artifacts"][0]["artifact_id"]

    run_dir, meta = resolve_artifact(aid, "chat-prev")
    assert run_dir.name == "run1"
    assert meta["filename"] == "note.md"

    data, mime, filename = read_artifact_bytes(aid, "chat-prev")
    assert data == b"**bold**"
    assert filename == "note.md"
    assert mime.startswith("text/")

    preview = preview_artifact(aid, "chat-prev")
    assert preview is not None
    assert preview["kind"] == "text"
    assert preview["text"] == "**bold**"


def test_path_traversal_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    safe = src / "ok.txt"
    safe.write_text("ok", encoding="utf-8")
    manifest = register_run_artifacts("chat-guard", "default", "w", "run-g", 0, [safe])
    aid = manifest["artifacts"][0]["artifact_id"]
    run_dir = chat_session_dir("chat-guard") / "run-g"
    manifest_path = run_dir / MANIFEST_NAME
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["artifacts"][0]["relative_path"] = "../secrets.txt"
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="path traversal|invalid relative_path"):
        resolve_artifact(aid, "chat-guard")


def test_purge_expired_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f = src / "x.txt"
    f.write_text("x", encoding="utf-8")
    register_run_artifacts("chat-purge", "default", "w", "expired-run", 0, [f])
    run_dir = chat_session_dir("chat-purge") / "expired-run"
    manifest_path = run_dir / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = time.time() - 10
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert run_dir.is_dir()
    result = purge_expired_runs()
    assert result["purged"] == 1
    assert not run_dir.exists()


def test_delete_artifact_and_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f = src / "del.txt"
    f.write_text("bye", encoding="utf-8")
    manifest = register_run_artifacts("chat-del", "default", "w", "run-del", 0, [f])
    aid = manifest["artifacts"][0]["artifact_id"]

    from duckclaw.sandbox_artifacts import delete_artifact, delete_run, get_run

    delete_artifact(aid, "chat-del")
    assert get_run("run-del", "chat-del") is None

    register_run_artifacts("chat-del", "default", "w", "run-del-2", 0, [f])
    delete_run("run-del-2", "chat-del")
    assert get_run("run-del-2", "chat-del") is None


def test_list_all_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    a = src / "a.txt"
    a.write_text("a", encoding="utf-8")
    register_run_artifacts("chat-a", "default", "w", "r1", 0, [a])
    register_run_artifacts("chat-b", "default", "w", "r2", 0, [a])

    from duckclaw.sandbox_artifacts import list_all_runs

    all_runs = list_all_runs(limit=10)
    assert len(all_runs) == 2
    filtered = list_all_runs(limit=10, chat_id_filter="chat-a")
    assert len(filtered) == 1
    assert filtered[0]["run_id"] == "r1"


def test_purge_keeps_active_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f = src / "keep.txt"
    f.write_text("keep", encoding="utf-8")
    register_run_artifacts("chat-keep", "default", "w", "active-run", 0, [f])
    run_dir = chat_session_dir("chat-keep") / "active-run"
    assert purge_expired_runs()["purged"] == 0
    assert run_dir.is_dir()
