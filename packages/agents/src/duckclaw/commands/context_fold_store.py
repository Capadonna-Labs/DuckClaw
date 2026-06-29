"""Persistencia del resumen compactado de hilo en la bóveda DuckDB conectada."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from duckclaw.commands.chat_state import get_chat_state, set_chat_state_via_typed_command

_log = logging.getLogger(__name__)

CONTEXT_FOLD_KEY = "context_fold_summary"


def context_fold_persist_enabled() -> bool:
    """Persistir fold en vault; desactivar con DUCKCLAW_CONTEXT_FOLD_PERSIST=0."""
    raw = (os.environ.get("DUCKCLAW_CONTEXT_FOLD_PERSIST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _vault_path_usable(vault_db_path: str) -> str:
    path = (vault_db_path or "").strip()
    if not path or path == ":memory:":
        return ""
    try:
        resolved = str(Path(path).expanduser().resolve())
    except OSError:
        resolved = path
    if not os.path.isfile(resolved):
        return ""
    return resolved


def _open_vault_readonly(vault_db_path: str) -> Any | None:
    resolved = _vault_path_usable(vault_db_path)
    if not resolved:
        return None
    try:
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly

        return GatewayDbEphemeralReadonly(resolved)
    except Exception as exc:
        _log.warning("context_fold_store: no se pudo abrir vault %s: %s", resolved[-96:], exc)
        return None


def load_context_fold_summary(vault_db_path: str, chat_id: str) -> str:
    """
    Lee el resumen compactado previo desde ``agent_config`` de la bóveda.

    Se rehidrata antes del fold manual o automático.
    """
    if not context_fold_persist_enabled():
        return ""
    vault_handle = _open_vault_readonly(vault_db_path)
    if vault_handle is None:
        return ""
    try:
        return (get_chat_state(vault_handle, chat_id, CONTEXT_FOLD_KEY) or "").strip()
    except Exception as exc:
        _log.warning("context_fold_store: load failed chat=%s: %s", chat_id, exc)
        return ""


def save_context_fold_summary(
    vault_db_path: str,
    chat_id: str,
    summary: str,
    *,
    tenant_id: str = "default",
) -> bool:
    """
    Persiste ``analytical_summary`` en la bóveda vía typed command (RO-safe).

    Retorna True si la escritura se encoló/completó sin error.
    """
    if not context_fold_persist_enabled():
        return False
    text = (summary or "").strip()
    if not text:
        return False
    resolved = _vault_path_usable(vault_db_path)
    if not resolved:
        return False
    vault_handle = _open_vault_readonly(resolved)
    if vault_handle is None:
        return False
    try:
        ok, err = set_chat_state_via_typed_command(
            vault_handle,
            chat_id,
            CONTEXT_FOLD_KEY,
            text[:16384],
            tenant_id=(tenant_id or "default").strip() or "default",
        )
        if not ok:
            _log.warning("context_fold_store: save failed chat=%s: %s", chat_id, err)
        return ok
    except Exception as exc:
        _log.warning("context_fold_store: save exception chat=%s: %s", chat_id, exc)
        return False


__all__ = [
    "CONTEXT_FOLD_KEY",
    "context_fold_persist_enabled",
    "load_context_fold_summary",
    "save_context_fold_summary",
]
