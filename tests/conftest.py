"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Permite `from scripts.foo import ...` en tests (p. ej. sanitize_traces_for_gemma).
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# API Gateway y db-writer exigen REDIS_URL o DUCKCLAW_REDIS_URL (sin fallback en código).
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
