"""Incremental folder sync planning for Obsidian / server-path RAG sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from duckclaw.forge.rag.knowledge_core import (
    KnowledgeDocumentPayload,
    build_document_payload,
    iter_allowed_files,
)


@dataclass(frozen=True)
class FolderSyncPlan:
    to_upsert: list[KnowledgeDocumentPayload]
    to_deactivate: list[str]
    scanned: int
    skipped: int


def plan_folder_sync(
    *,
    root: Path,
    source_id: str,
    existing: dict[str, tuple[str, str]],
    max_chars: int = 3200,
) -> FolderSyncPlan:
    """Compare disk files with indexed checksums and return upsert/deactivate actions."""
    base = root if root.is_dir() else root.parent
    files = iter_allowed_files(root)
    seen_paths: set[str] = set()
    to_upsert: list[KnowledgeDocumentPayload] = []
    skipped = 0

    for file_path in files:
        payload = build_document_payload(
            root=base,
            path=file_path,
            source_id=source_id,
            max_chars=max_chars,
        )
        rel = str(payload.document["relative_path"])
        seen_paths.add(rel)
        prior = existing.get(rel)
        if prior and prior[1] == payload.document["checksum"]:
            skipped += 1
            continue
        to_upsert.append(payload)

    to_deactivate = [
        doc_id
        for rel, (doc_id, _checksum) in existing.items()
        if rel not in seen_paths
    ]
    return FolderSyncPlan(
        to_upsert=to_upsert,
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
