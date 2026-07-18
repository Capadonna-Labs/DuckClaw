"""Corpus del cliente admin HTTP: facade + módulos `services/admin/*`."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SERVICES = _ROOT / "apps/duckclaw-admin/src/services"
_ADMIN_MOD = _SERVICES / "admin"


def admin_service_corpus() -> str:
    """Texto concatenado del facade y todos los módulos de dominio."""
    parts = [(_SERVICES / "adminService.ts").read_text(encoding="utf-8")]
    for path in sorted(_ADMIN_MOD.glob("*.ts")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
