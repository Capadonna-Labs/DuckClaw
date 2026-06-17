"""Compatibility loader for Capadonna-Driller plugin modules.

Product-specific runtime lives outside this monorepo. DuckClaw keeps this small
facade so command handlers can delegate and degrade gracefully when the external
checkout is not configured.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_CAPADONNA_MISSING_MSG = (
    "Extensión Capadonna-Driller no configurada. "
    "Define CAPADONNA_DRILLER_ROOT apuntando al checkout de Capadonna-Driller."
)


def capadonna_missing_message() -> str:
    return _CAPADONNA_MISSING_MSG


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


def push_capadonna_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    """Enqueue a product state delta when Capadonna-Driller is configured."""
    mod = load_capadonna_lib("quant_state_delta")
    fn = getattr(mod, "push_quant_state_delta_sync", None) if mod is not None else None
    if not callable(fn):
        return False
    return bool(fn(payload, duckclaw_db=duckclaw_db))


def dispatch_capadonna_fly_command(
    command_name: str,
    db: Any,
    chat_id: Any,
    args: str,
    **kwargs: Any,
) -> str | None:
    """Dispatch a Capadonna fly command when the external bridge is available."""
    command = (command_name or "").strip().lower().replace("_", "-")
    if not command:
        return None

    fly = load_capadonna_lib("fly_commands")
    fly_dispatch = getattr(fly, "dispatch", None) if fly is not None else None
    if callable(fly_dispatch):
        result = fly_dispatch(command, db, chat_id, args, **kwargs)
        if result is not None:
            return result

    bridge = load_capadonna_lib(f"{command.replace('-', '_')}_bridge")
    if bridge is None:
        bridge = load_capadonna_lib(f"{command}_bridge")
    dispatch = getattr(bridge, "dispatch_fly_command", None) if bridge is not None else None
    if callable(dispatch):
        return dispatch(db, chat_id, args, **kwargs)
    return None


def _capadonna_tool_context() -> ModuleType | None:
    return load_capadonna_lib("".join(("quant", "_tool_context")))


def capadonna_tool_tenant_id() -> str:
    ctx = _capadonna_tool_context()
    fn = getattr(ctx, "get_quant_tool_tenant_id", None) if ctx is not None else None
    return fn() if callable(fn) else ""


def capadonna_tool_user_id() -> str:
    ctx = _capadonna_tool_context()
    fn = getattr(ctx, "get_quant_tool_user_id", None) if ctx is not None else None
    return fn() if callable(fn) else ""


def capadonna_tool_chat_id() -> str:
    ctx = _capadonna_tool_context()
    fn = getattr(ctx, "get_quant_tool_chat_id", None) if ctx is not None else None
    return fn() if callable(fn) else ""


def capadonna_tool_worker_id() -> str:
    ctx = _capadonna_tool_context()
    fn = getattr(ctx, "get_quant_tool_worker_id", None) if ctx is not None else None
    return fn() if callable(fn) else ""


def set_capadonna_tool_context(
    *,
    tenant_id: str = "",
    user_id: str = "",
    db_path: str = "",
) -> None:
    ctx = _capadonna_tool_context()
    if ctx is None:
        return
    if db_path:
        setter = getattr(ctx, "set_quant_tool_db_path", None)
        if callable(setter):
            setter(db_path)
    if tenant_id:
        setter = getattr(ctx, "set_quant_tool_tenant_id", None)
        if callable(setter):
            setter((tenant_id or "default").strip() or "default")
    if user_id:
        setter = getattr(ctx, "set_quant_tool_user_id", None)
        if callable(setter):
            setter((user_id or "default").strip() or "default")


def load_capadonna_code_decision_service() -> ModuleType | None:
    """Load Capadonna HITL code-decision helpers when the extension is configured."""
    return load_capadonna_lib("code_decision_service")


def approve_capadonna_code_decision(db: Any, **kwargs: Any) -> dict[str, Any] | None:
    mod = load_capadonna_code_decision_service()
    fn = getattr(mod, "approve_code_decision", None) if mod is not None else None
    if not callable(fn):
        return None
    return fn(db, **kwargs)


def reject_capadonna_code_decision(db: Any, **kwargs: Any) -> dict[str, Any] | None:
    mod = load_capadonna_code_decision_service()
    fn = getattr(mod, "reject_code_decision", None) if mod is not None else None
    if not callable(fn):
        return None
    return fn(db, **kwargs)


__all__ = [
    "approve_capadonna_code_decision",
    "capadonna_missing_message",
    "capadonna_tool_chat_id",
    "capadonna_tool_tenant_id",
    "capadonna_tool_user_id",
    "capadonna_tool_worker_id",
    "dispatch_capadonna_fly_command",
    "load_capadonna_code_decision_service",
    "load_capadonna_lib",
    "push_capadonna_state_delta_sync",
    "reject_capadonna_code_decision",
    "set_capadonna_tool_context",
]
