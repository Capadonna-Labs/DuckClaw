"""
Aplica state deltas en proceso (perfil Spawn sin db-writer).

Importa handlers de ``services/db-writer`` si están en PYTHONPATH; si no, añade
temporalmente ese directorio al path del repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_writer_import_attempted = False
_writer_import_ok = False


def _repo_root() -> Path:
    rr = (sys.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if rr:
        return Path(rr).resolve()
    # packages/shared/src/duckclaw/spawn_inline_delta.py → repo
    return Path(__file__).resolve().parents[4]


def _ensure_db_writer_import_path() -> bool:
    global _writer_import_attempted, _writer_import_ok
    if _writer_import_attempted:
        return _writer_import_ok
    _writer_import_attempted = True
    writer_dir = _repo_root() / "services" / "db-writer"
    if writer_dir.is_dir():
        p = str(writer_dir)
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import context_injection_handler  # noqa: F401
        import visual_state_delta_handler  # noqa: F401

        _writer_import_ok = True
    except ImportError:
        _writer_import_ok = False
    return _writer_import_ok


def apply_context_injection_message_sync(message: str) -> bool:
    """Ejecuta CONTEXT_INJECTION inline (mismo cuerpo que db-writer)."""
    if not _ensure_db_writer_import_path():
        return False
    try:
        from context_injection_handler import _sync_handle_context_injection

        _sync_handle_context_injection(message)
        return True
    except Exception:
        return False


def apply_visual_state_delta_message_sync(message: str) -> bool:
    """Ejecuta VISUAL_STATE_DELTA inline (mismo cuerpo que db-writer)."""
    if not _ensure_db_writer_import_path():
        return False
    try:
        from visual_state_delta_handler import _sync_handle_visual_state_delta

        _sync_handle_visual_state_delta(message)
        return True
    except Exception:
        return False


def apply_context_injection_delta_sync(delta: Any) -> bool:
    if hasattr(delta, "model_dump_json"):
        payload = delta.model_dump_json()
    elif hasattr(delta, "model_dump"):
        payload = json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)
    elif isinstance(delta, dict):
        payload = json.dumps(delta, ensure_ascii=False)
    else:
        payload = str(delta)
    return apply_context_injection_message_sync(payload)
