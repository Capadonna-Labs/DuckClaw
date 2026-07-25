"""Load API gateway FastAPI app for desktop sidecar (dev + PyInstaller)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _ensure_gateway_path(repo: Path) -> None:
    gateway_dir = repo / "services" / "api-gateway"
    writer_dir = repo / "services" / "db-writer"
    for p in (str(gateway_dir), str(writer_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)


_repo = _repo_root()
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_repo))
_ensure_gateway_path(_repo)

from asgi_app import app  # noqa: E402 — services/api-gateway/asgi_app.py

__all__ = ["app"]
