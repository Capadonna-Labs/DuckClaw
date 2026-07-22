"""Tests for dual-write of agent outputs to all OUTPUT roots."""

from __future__ import annotations

from pathlib import Path


def test_replicate_file_to_all_output_roots(tmp_path: Path) -> None:
    from duckclaw.forge.rag.knowledge_paths import replicate_file_to_all_output_roots

    local = tmp_path / "local_output"
    drive = tmp_path / "drive_output"
    local.mkdir()
    drive.mkdir()
    rel = Path("Alcaldia/informes_mensuales/INFORME.docx")
    primary = local / rel
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b"informe-bytes")

    paths = replicate_file_to_all_output_roots(primary, roots=[local, drive])
    assert len(paths) == 2
    assert Path(paths[0]).is_file()
    assert Path(paths[1]).is_file()
    assert (drive / rel).read_bytes() == b"informe-bytes"


def test_replicate_idempotent_when_already_on_all_roots(tmp_path: Path) -> None:
    from duckclaw.forge.rag.knowledge_paths import replicate_file_to_all_output_roots

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    rel = Path("out/doc.docx")
    (a / rel).parent.mkdir(parents=True)
    (a / rel).write_text("x", encoding="utf-8")
    paths = replicate_file_to_all_output_roots(a / rel, roots=[a, b])
    assert (b / rel).read_text(encoding="utf-8") == "x"
    assert len(paths) == 2
