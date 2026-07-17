"""Productividad artifacts — storage promote + index handlers."""

from __future__ import annotations

from pathlib import Path

import duckdb

from duckclaw.productivity_artifacts import (
    promote_files_to_storage,
    storage_root,
    unlink_storage_uri,
)
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_command_handlers import dispatch_command


def test_promote_files_to_storage_copies_under_root(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    f = src / "chart.png"
    f.write_bytes(b"\x89PNG\r\n")
    base = tmp_path / "storage" / "artifacts"
    rows = promote_files_to_storage(
        [f],
        tenant_id="t1",
        owner_email="a@ex.com",
        source_kind="sandbox",
        source_ref="run123",
        title_prefix="Sandbox run",
        base=base,
    )
    assert len(rows) == 1
    assert rows[0]["lane"] == "storage"
    dest = Path(rows[0]["uri"])
    assert dest.is_file()
    dest.relative_to(storage_root(base=base))


def test_unlink_storage_uri_only_under_root(tmp_path: Path) -> None:
    base = tmp_path / "storage" / "artifacts"
    base.mkdir(parents=True)
    inside = base / "t1" / "x.bin"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"abc")
    outside = tmp_path / "evil.bin"
    outside.write_bytes(b"no")
    assert unlink_storage_uri(str(inside), base=base) is True
    assert not inside.exists()
    assert unlink_storage_uri(str(outside), base=base) is False
    assert outside.exists()


def test_register_vault_artifact_from_path_enqueues(tmp_path: Path, monkeypatch) -> None:
    from duckclaw import productivity_artifacts as pa

    f = tmp_path / "out" / "note.md"
    f.parent.mkdir(parents=True)
    f.write_text("# hi", encoding="utf-8")
    captured: list[dict] = []

    def _fake_enqueue(payloads, *, actor_email: str):
        captured.extend(payloads)
        return ["task-1"]

    monkeypatch.setattr(pa, "enqueue_productivity_upserts", _fake_enqueue)
    row = pa.register_vault_artifact_from_path(
        f,
        tenant_id="default",
        owner_email="u@ex.com",
        source_kind="write_output",
        source_ref="note.md",
    )
    assert row is not None
    assert row["lane"] == "vault"
    assert row["artifact_id"].startswith("pvlt_")
    assert len(captured) == 1
    assert captured[0]["filename"] == "note.md"


def test_promote_storage_file_to_vault(tmp_path: Path, monkeypatch) -> None:
    from duckclaw import productivity_artifacts as pa

    storage = tmp_path / "storage" / "artifacts"
    src_dir = storage / "t1"
    src_dir.mkdir(parents=True)
    src = src_dir / "part_abc123_chart.png"
    src.write_bytes(b"png")

    vault = tmp_path / "vault_out"
    vault.mkdir()
    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", str(vault))
    monkeypatch.setattr(pa, "enqueue_productivity_upserts", lambda payloads, *, actor_email: ["t"])

    result = pa.promote_storage_file_to_vault(
        source_uri=str(src),
        tenant_id="t1",
        owner_email="a@ex.com",
        title="Chart",
        storage_base=storage,
    )
    assert result["filename"] == "chart.png"
    assert result["relative_path"] == "Productividad/chart.png"
    dest = vault / "Productividad" / "chart.png"
    assert dest.is_file()


def test_productivity_artifact_upsert_and_soft_delete(tmp_path: Path) -> None:
    db = duckdb.connect(str(tmp_path / "hub.duckdb"))
    run_pending_migrations(db)
    dispatch_command(
        db,
        {
            "command_type": "upsert_productivity_artifact",
            "artifact_id": "part_test1",
            "tenant_id": "default",
            "owner_email": "a@ex.com",
            "lane": "storage",
            "title": "Chart",
            "filename": "chart.png",
            "uri": "/tmp/nope",
            "source_kind": "sandbox",
            "source_ref": "run1",
            "mime": "image/png",
            "byte_size": 10,
        },
    )
    row = db.execute(
        "SELECT active, title FROM main.admin_productivity_artifacts WHERE artifact_id = 'part_test1'"
    ).fetchone()
    assert row is not None and row[0] is True and str(row[1]) == "Chart"
    dispatch_command(
        db,
        {
            "command_type": "soft_delete_productivity_artifact",
            "artifact_id": "part_test1",
            "tenant_id": "default",
            "actor_email": "a@ex.com",
        },
    )
    row2 = db.execute(
        "SELECT active FROM main.admin_productivity_artifacts WHERE artifact_id = 'part_test1'"
    ).fetchone()
    assert row2 is not None and row2[0] is False
