"""Escritura atómica con backup .bak (spec Sovereign Wizard §6 rollback)."""

from __future__ import annotations

import shutil
from pathlib import Path


def atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """
    Escribe ``content`` en ``path``. Si el archivo existía, copia a ``path.bak`` antes.
    Si la escritura falla, intenta restaurar desde ``.bak``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    try:
        path.write_text(content, encoding=encoding)
    except Exception:
        if backup and backup.is_file():
            try:
                shutil.copy2(backup, path)
            except Exception:
                pass
        raise
