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
    # Desktop/Lite runs one process with inline writes (no db-writer) — services/db-writer
    # must NOT be added here: it has its own core.config with an unrelated Settings class,
    # and both dirs define a top-level `core` package, so whichever lands first in sys.path
    # wins for every `core.*` import project-wide (this shadowed api-gateway's own
    # core.config.settings.VERSION with db-writer's Settings, which has no such field).
    gateway_dir = repo / "services" / "api-gateway"
    if str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))


_repo = _repo_root()
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_repo))
_ensure_gateway_path(_repo)

from asgi_app import app  # noqa: E402 — services/api-gateway/asgi_app.py

__all__ = ["app"]
