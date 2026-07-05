"""Staging disk for browser uploads — Gateway writes bytes; indexer ingests."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

_STAGING_ENV = "DUCKCLAW_KNOWLEDGE_UPLOAD_STAGING"


def upload_staging_root() -> Path:
    raw = (os.environ.get(_STAGING_ENV) or "").strip()
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        from duckclaw.gateway_db import get_gateway_db_path

        hub = (get_gateway_db_path() or "").strip()
        base = Path(hub).expanduser().resolve().parent if hub else Path.cwd()
        root = (base / "knowledge_upload_staging").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def stage_browser_upload(*, job_id: str, files: list[tuple[str, bytes]]) -> Path:
    """Persist uploaded files under ``{staging_root}/{job_id}/``."""
    dest = upload_staging_root() / job_id
    dest.mkdir(parents=True, exist_ok=True)
    manifest: list[str] = []
    for filename, data in files:
        safe_name = Path(filename.replace("\\", "/")).name.strip() or "upload.txt"
        target = dest / safe_name
        target.write_bytes(data)
        manifest.append(safe_name)
    (dest / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return dest


def read_staged_upload_manifest(staging_dir: str | Path) -> list[Path]:
    root = Path(staging_dir).expanduser().resolve()
    manifest_path = root / "_manifest.json"
    if manifest_path.is_file():
        names = json.loads(manifest_path.read_text(encoding="utf-8"))
        return [root / str(name) for name in names if (root / str(name)).is_file()]
    return sorted(p for p in root.iterdir() if p.is_file() and p.name != "_manifest.json")


def cleanup_staging_dir(staging_dir: str | Path) -> None:
    root = Path(staging_dir).expanduser().resolve()
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
