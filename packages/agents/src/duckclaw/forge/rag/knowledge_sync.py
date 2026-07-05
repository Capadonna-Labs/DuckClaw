"""Incremental folder sync planning for Obsidian / server-path RAG sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from duckclaw.forge.rag.knowledge_core import (
    iter_allowed_files,
    read_document_text,
    safe_relative_path,
    sha256_text,
)
from duckclaw.forge.rag.markitdown_convert import MARKITDOWN_SUFFIXES


@dataclass(frozen=True)
class FolderSyncPlan:
    to_upsert_paths: list[Path]
    to_deactivate: list[str]
    scanned: int
    skipped: int


def plan_folder_sync(
    *,
    root: Path,
    source_id: str,
    existing: dict[str, tuple[str, str, int]],
    force: bool = False,
) -> FolderSyncPlan:
    """Compare disk files with indexed checksums; return paths needing ingest."""
    base = root if root.is_dir() else root.parent
    files = iter_allowed_files(root)
    seen_paths: set[str] = set()
    to_upsert_paths: list[Path] = []
    skipped = 0

    for file_path in files:
        relative_path = safe_relative_path(base, file_path)
        seen_paths.add(relative_path)
        prior = existing.get(relative_path)
        if prior and not force:
            _doc_id, prior_checksum, prior_byte_size = prior
            if prior_byte_size == file_path.stat().st_size:
                suffix = file_path.suffix.lower()
                if suffix in MARKITDOWN_SUFFIXES:
                    skipped += 1
                    continue
                text, _mime = read_document_text(file_path)
                if sha256_text(text) == prior_checksum:
                    skipped += 1
                    continue
        to_upsert_paths.append(file_path)

    to_deactivate = [
        doc_id
        for rel, (doc_id, _checksum, _byte_size) in existing.items()
        if rel not in seen_paths
    ]
    return FolderSyncPlan(
        to_upsert_paths=to_upsert_paths,
        to_deactivate=to_deactivate,
        scanned=len(files),
        skipped=skipped,
    )


def folder_mtime_fingerprint(root: Path) -> float:
    """Cheap change detector: max mtime of ingest-eligible files under root."""
    try:
        files = iter_allowed_files(root)
    except (FileNotFoundError, ValueError):
        return 0.0
    if not files:
        return 0.0
    return max(p.stat().st_mtime for p in files)
