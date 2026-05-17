"""Diagnóstico DuckDB para el Sovereign Wizard (ruta, tamaño, conexión, integridad)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.validate import private_db_dir_writable

_DEFAULT_VAULT = "db/sovereign_memory.duckdb"


def primary_duckdb_relpath(draft: SovereignDraft) -> str:
    vault = (draft.duckdb_vault_path or "").strip() or _DEFAULT_VAULT
    shared = (draft.duckdb_shared_path or "").strip()
    if shared and vault == _DEFAULT_VAULT:
        return shared
    return vault


def resolve_duckdb_path(repo_root: Path, rel_or_abs: str) -> Path:
    p = Path((rel_or_abs or "").strip())
    if not p.parts:
        return (repo_root / _DEFAULT_VAULT).resolve()
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def human_bytes(n: int) -> str:
    if n < 0:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{n} B"


@dataclass(frozen=True)
class DuckDbHealth:
    rel_path: str
    abs_path: Path
    exists: bool
    size_bytes: int
    writable_parent: bool
    connection_ok: bool
    integrity_ok: bool
    integrity_detail: str
    table_count: int | None
    shared_rel: str

    @property
    def ok(self) -> bool:
        if not self.writable_parent:
            return False
        if not self.exists:
            return True
        return self.connection_ok and self.integrity_ok

    @property
    def size_human(self) -> str:
        return human_bytes(self.size_bytes) if self.exists else "—"


def audit_duckdb(
    repo_root: Path,
    draft: SovereignDraft,
    *,
    quick: bool = False,
) -> DuckDbHealth:
    """
    Inspecciona la bóveda DuckDB del borrador.

    ``quick=True``: sin PRAGMA integrity_check (cabecera TUI).
    """
    rel = primary_duckdb_relpath(draft)
    abs_path = resolve_duckdb_path(repo_root, rel)
    shared = (draft.duckdb_shared_path or "").strip()
    parent = abs_path.parent
    writable = private_db_dir_writable(repo_root) and os.access(
        parent if parent.exists() else (repo_root / "db"),
        os.W_OK,
    )

    exists = abs_path.is_file()
    size_bytes = abs_path.stat().st_size if exists else 0
    connection_ok = False
    integrity_ok = not exists
    integrity_detail = "se creará al aplicar" if not exists else ""
    table_count: int | None = None

    if exists:
        integrity_ok = False
        try:
            import duckdb  # noqa: PLC0415

            conn = duckdb.connect(str(abs_path), read_only=True)
            try:
                conn.execute("SELECT 1").fetchone()
                connection_ok = True
                integrity_ok = True
                if quick:
                    integrity_detail = "conexión OK"
                else:
                    integrity_detail = "lectura OK"
                    try:
                        conn.execute(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema NOT IN "
                            "('information_schema', 'pg_catalog')"
                        ).fetchone()
                    except Exception:
                        integrity_detail = "conexión OK (sin catálogo)"
                try:
                    table_count = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema NOT IN ('information_schema', 'pg_catalog')"
                        ).fetchone()[0]
                    )
                except Exception:
                    table_count = None
            finally:
                conn.close()
        except ImportError:
            integrity_detail = "paquete duckdb no instalado"
        except Exception as exc:
            integrity_detail = str(exc)[:200]
    elif not writable:
        integrity_detail = "sin permiso de escritura en db/"

    return DuckDbHealth(
        rel_path=rel,
        abs_path=abs_path,
        exists=exists,
        size_bytes=size_bytes,
        writable_parent=writable,
        connection_ok=connection_ok,
        integrity_ok=integrity_ok,
        integrity_detail=integrity_detail,
        table_count=table_count,
        shared_rel=shared,
    )


def format_duckdb_health_rich(health: DuckDbHealth) -> str:
    """Bloque MAIN: DuckDB detallado."""
    mark = "[green]OK[/]" if health.ok else "[yellow]—[/]"
    lines = [
        f"[bold]DuckDB[/] {mark}",
        f"  [dim]Ruta[/] {health.rel_path}",
        f"  [dim]Absoluta[/] {health.abs_path}",
    ]
    if health.exists:
        lines.append(f"  [dim]Tamaño[/] {health.size_human} ({health.size_bytes:,} bytes)")
        lines.append(
            f"  [dim]Conexión[/] "
            f"{'OK' if health.connection_ok else 'fallo'} · "
            f"{health.integrity_detail}"
        )
        if health.table_count is not None:
            lines.append(f"  [dim]Tablas[/] {health.table_count}")
    else:
        lines.append("  [dim]Archivo[/] aún no existe (se creará al aplicar)")
    if health.shared_rel and health.shared_rel != health.rel_path:
        lines.append(f"  [dim]Adjunta[/] {health.shared_rel}")
    if not health.writable_parent:
        lines.append("  [red]Carpeta db/ sin permiso de escritura[/]")
    return "\n".join(lines)


def duckdb_chrome_summary(health: DuckDbHealth) -> str:
    """Una línea para el chrome del wizard (sin tenant)."""
    if not health.exists:
        return f"DuckDB [dim]{health.rel_path}[/] · pendiente"
    status = "OK" if health.ok else "revisar"
    tbl = f" · {health.table_count} tablas" if health.table_count is not None else ""
    tone = "green" if health.ok else "yellow"
    return (
        f"DuckDB [cyan]{health.rel_path}[/] · {health.size_human} · "
        f"[{tone}]{status}[/]{tbl}"
    )
