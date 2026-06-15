"""Compatibility loader for Capadonna-Driller plugin modules.

Quant/IBKR runtime code lives outside this monorepo. DuckClaw keeps this small
facade so legacy command handlers can import a stable module and gracefully
degrade when the external checkout is not configured.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _candidate_lib_dirs() -> list[Path]:
    raw_root = (os.environ.get("CAPADONNA_DRILLER_ROOT") or "").strip()
    if not raw_root:
        return []

    root = Path(raw_root).expanduser()
    return [
        root / "workers" / "duckclaw" / "lib",
        root,
    ]


def _ensure_capadonna_lib_on_path() -> None:
    for path in _candidate_lib_dirs():
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        path_text = str(resolved)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def load_capadonna_lib(module_name: str) -> ModuleType | None:
    """Load a Capadonna-Driller module by its canonical external module name."""
    name = (module_name or "").strip()
    if not name:
        return None

    _ensure_capadonna_lib_on_path()
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def dispatch_capadonna_fly_command(
    command_name: str,
    db: Any,
    chat_id: Any,
    args: str,
    **kwargs: Any,
) -> str | None:
    """Dispatch a Capadonna fly command when the external bridge is available."""
    command = (command_name or "").strip().lower()
    if not command:
        return None

    bridge = load_capadonna_lib(f"{command}_bridge")
    dispatch = getattr(bridge, "dispatch_fly_command", None) if bridge is not None else None
    if not callable(dispatch):
        return None
    return dispatch(db, chat_id, args, **kwargs)


__all__ = ["dispatch_capadonna_fly_command", "load_capadonna_lib"]
