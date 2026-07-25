"""ASGI app export for desktop sidecar (dev + PyInstaller)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent

os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_REPO))

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.gateway_bootstrap import apply_gateway_bootstrap

apply_gateway_bootstrap()

from gateway_app_factory import app  # noqa: E402

__all__ = ["app"]
