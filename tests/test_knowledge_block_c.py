from __future__ import annotations

import json

import pytest


def test_scan_knowledge_folder_skips_obsidian_hidden_files(tmp_path) -> None:
    from duckclaw.forge.rag.knowledge_core import scan_knowledge_folder

    root = tmp_path / "vault"
    obsidian = root / ".obsidian"
    obsidian.mkdir(parents=True)
    (root / "nota.md").write_text("# Hola", encoding="utf-8")
    (obsidian / "workspace.json").write_text("{}", encoding="utf-8")

    scan = scan_knowledge_folder(root)
    assert scan.file_count == 1
    assert scan.skipped_hidden >= 1


def test_plan_folder_sync_skips_unchanged_and_detects_changes(tmp_path) -> None:
    from duckclaw.forge.rag.knowledge_core import build_document_payload, sha256_text
    from duckclaw.forge.rag.knowledge_sync import plan_folder_sync

    root = tmp_path / "vault"
    root.mkdir()
    doc = root / "note.md"
    doc.write_text("# Note\nv1", encoding="utf-8")

    payload = build_document_payload(root=root, path=doc, source_id="ksrc_obs")
    byte_size = int(payload.document["byte_size"])
    existing = {
        "note.md": (str(payload.document["document_id"]), str(payload.document["checksum"]), byte_size),
    }

    unchanged = plan_folder_sync(root=root, source_id="ksrc_obs", existing=existing)
    assert unchanged.scanned == 1
    assert unchanged.skipped == 1
    assert unchanged.to_upsert_paths == []
    assert unchanged.to_deactivate == []

    doc.write_text("# Note\nv2", encoding="utf-8")
    changed = plan_folder_sync(root=root, source_id="ksrc_obs", existing=existing)
    assert changed.skipped == 0
    assert len(changed.to_upsert_paths) == 1

    doc.unlink()
    removed = plan_folder_sync(root=root, source_id="ksrc_obs", existing=existing)
    assert removed.to_deactivate == [payload.document["document_id"]]
    assert removed.to_upsert_paths == []


def test_resolve_truncated_gmail_path_uses_allowed_root(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.rag.knowledge_paths import resolve_knowledge_ingest_uri

    vault = tmp_path / "MacMiniVault"
    vault.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(vault))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)

    truncated = "/Users/workstation/Library/CloudStorage/GoogleDrive-user@gmail"
    assert resolve_knowledge_ingest_uri(truncated) == str(vault.resolve())
    assert resolve_knowledge_ingest_uri("") == str(vault.resolve())


def test_validate_knowledge_ingest_root_requires_allowlist(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.rag.knowledge_paths import validate_knowledge_ingest_root

    vault = tmp_path / "obsidian"
    vault.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(vault))
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)

    assert validate_knowledge_ingest_root(str(vault)) == vault.resolve()

    outside = tmp_path / "other"
    outside.mkdir()
    with pytest.raises(ValueError, match="fuera"):
        validate_knowledge_ingest_root(str(outside))


def test_resolve_knowledge_output_path_writes_under_root(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.rag.knowledge_paths import resolve_knowledge_output_path

    out_root = tmp_path / "output"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", raising=False)

    target = resolve_knowledge_output_path(relative_path="reports/summary.md")
    assert target == (out_root / "reports" / "summary.md").resolve()

    with pytest.raises(ValueError, match="outside"):
        resolve_knowledge_output_path(relative_path="../escape.md")


def test_write_output_document_tool(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.skills.write_output_document_bridge import write_output_document

    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC", "false")

    raw = write_output_document("notes/answer.md", "# Respuesta\n\nContenido generado.")
    payload = json.loads(raw)
    assert payload["relative_path"] == "notes/answer.md"
    assert (out_root / "notes" / "answer.md").read_text(encoding="utf-8").startswith("# Respuesta")


def test_write_output_document_respects_explicit_py_extension(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.skills.write_output_document_bridge import write_output_document

    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC", "false")

    raw = write_output_document("scripts/hola.py", "print('hola')")
    payload = json.loads(raw)
    assert payload["relative_path"] == "scripts/hola.py"
    assert (out_root / "scripts" / "hola.py").read_text(encoding="utf-8") == "print('hola')"


def test_normalize_output_relative_path() -> None:
    from duckclaw.forge.rag.knowledge_paths import normalize_output_relative_path

    assert normalize_output_relative_path("informe") == "informe.md"
    assert normalize_output_relative_path("scripts/hola.py") == "scripts/hola.py"
    with pytest.raises(ValueError, match="conversión"):
        normalize_output_relative_path("scripts/hola.py", require_markdown=True)


def test_folder_mtime_fingerprint_changes_on_edit(tmp_path) -> None:
    from duckclaw.forge.rag.knowledge_sync import folder_mtime_fingerprint
    import time

    root = tmp_path / "vault"
    root.mkdir()
    doc = root / "a.md"
    doc.write_text("v1", encoding="utf-8")
    first = folder_mtime_fingerprint(root)
    time.sleep(0.02)
    doc.write_text("v2", encoding="utf-8")
    second = folder_mtime_fingerprint(root)
    assert second >= first


def test_enqueue_knowledge_command_is_fire_and_forget(monkeypatch) -> None:
    from duckclaw.forge.rag import knowledge_auto_sync

    polled = {"called": False}

    def fake_enqueue(command, *, db_path, user_id):
        return "k-task-1"

    def fake_poll(*_args, **_kwargs):
        polled["called"] = True
        return None

    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.enqueue_write_command",
        fake_enqueue,
    )
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.wait_write_task",
        fake_poll,
    )
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: "/tmp/hub.duckdb",
    )

    task_id = knowledge_auto_sync._enqueue_knowledge_command(object())
    assert task_id == "k-task-1"
    assert polled["called"] is False


def test_auto_sync_enabled_defaults_true(monkeypatch) -> None:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, auto_sync_poll_seconds

    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC", raising=False)
    assert auto_sync_enabled() is True
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC", "false")
    assert auto_sync_enabled() is False
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC_POLL_SEC", raising=False)
    assert auto_sync_poll_seconds() == 60


def test_execute_folder_sync_skips_unchanged_fingerprint(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.rag.knowledge_auto_sync import execute_folder_sync
    from duckclaw.forge.rag.knowledge_core import build_document_payload

    monkeypatch.setenv("DUCKCLAW_PROCESS_ROLE", "knowledge-indexer")
    vault = tmp_path / "vault"
    vault.mkdir()
    doc = vault / "note.md"
    doc.write_text("# Note", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", str(vault))

    payload = build_document_payload(root=vault, path=doc, source_id="ksrc_x")
    existing = {
        "note.md": (
            payload.document["document_id"],
            payload.document["checksum"],
            int(payload.document["byte_size"]),
        )
    }
    source = {
        "source_id": "ksrc_x",
        "tenant_id": "tenant_a",
        "project_id": "proj_a",
        "worker_uid": "",
        "source_kind": "folder",
        "source_uri": str(vault),
        "display_name": "Vault",
        "metadata": {},
    }

    first = execute_folder_sync(source=source, existing=existing, actor_email="test@test.com", force=False)
    assert first.skipped_reason == "no_changes"
    assert first.task_ids == []

    second = execute_folder_sync(source=source, existing=existing, actor_email="test@test.com", force=False)
    assert second.skipped_reason == "unchanged_fingerprint"


def test_write_output_document_includes_rag_sync_key(tmp_path, monkeypatch) -> None:
    from duckclaw.forge.skills.write_output_document_bridge import write_output_document

    out_root = tmp_path / "vault-out"
    out_root.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(out_root))
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_AUTO_SYNC", "false")

    raw = write_output_document("notes/answer.md", "# Respuesta\n\nContenido generado.")
    payload = json.loads(raw)
    assert payload["relative_path"] == "notes/answer.md"
    assert payload["rag_sync"]["synced"] is False
    assert payload["rag_sync"]["reason"] == "auto_sync_disabled"


def test_deactivate_knowledge_documents_handler(db_with_knowledge) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    con = db_with_knowledge
    dispatch_command(
        con,
        {
            "command_type": "deactivate_knowledge_documents",
            "tenant_id": "tenant_a",
            "source_id": "ksrc_a",
            "document_ids": ["kdoc_a"],
        },
    )
    row = con.execute(
        "SELECT active FROM main.admin_knowledge_documents WHERE document_id = 'kdoc_a'"
    ).fetchone()
    assert row is not None
    assert row[0] is False


@pytest.fixture
def db_with_knowledge():
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.admin_knowledge_sources
          (source_id, tenant_id, project_id, worker_uid, source_kind, source_uri, status)
        VALUES ('ksrc_a', 'tenant_a', 'proj_a', 'wrk_a', 'folder', '/docs', 'ready')
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_documents
          (document_id, source_id, relative_path, title, checksum)
        VALUES ('kdoc_a', 'ksrc_a', 'aws/iam.md', 'IAM', 'sha256:a')
        """
    )
    con.execute(
        """
        INSERT INTO main.admin_knowledge_chunks
          (chunk_id, document_id, source_id, tenant_id, project_id, worker_uid,
           chunk_index, content, content_hash, embedding_status)
        VALUES
          ('kchk_a', 'kdoc_a', 'ksrc_a', 'tenant_a', 'proj_a', 'wrk_a',
           0, 'IAM least privilege policies', 'h1', 'PENDING')
        """
    )
    yield con
    con.close()
