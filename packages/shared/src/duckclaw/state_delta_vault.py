"""Shared helpers for state-delta producers (vault handle release)."""

from __future__ import annotations

import os
from typing import Any


def _same_vault_db_path(lhs: str, rhs: str) -> bool:
    a, b = (lhs or "").strip(), (rhs or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def release_ro_vault_for_remote_writer(payload: dict[str, Any], duckclaw_db: Any | None) -> bool:
    """
    Close the gateway/worker handle on the same .duckdb path the remote writer will open.
    """
    if duckclaw_db is None:
        return False
    tgt = str(payload.get("target_db_path") or "").strip()
    db_path = str(getattr(duckclaw_db, "_path", "") or "").strip()
    if not _same_vault_db_path(tgt, db_path):
        return False
    release = getattr(duckclaw_db, "release_file_handle_for_external_writer", None)
    if callable(release):
        try:
            release()
            return True
        except Exception:
            return False
    if not bool(getattr(duckclaw_db, "_read_only", False)):
        return False
    susp = getattr(duckclaw_db, "suspend_readonly_file_handle", None)
    if not callable(susp):
        return False
    try:
        susp()
        return True
    except Exception:
        return False
