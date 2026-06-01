"""DuckDB/admin maintenance commands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _run_script(script_name: str, extra_args: list[str], *, dry_run: bool) -> None:
    script = _repo_root() / "scripts" / script_name
    argv = [sys.executable, str(script), *extra_args]
    if dry_run:
        typer.echo("dry-run: " + " ".join(argv))
        return
    proc = subprocess.run(argv, cwd=_repo_root(), text=True, check=False)
    raise typer.Exit(proc.returncode)


@app.command("bootstrap", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def bootstrap(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Aplica DDL idempotente a DuckDBs conocidas."""
    _run_script("bootstrap_dbs.py", list(ctx.args), dry_run=dry_run)


@app.command("check-locks")
def check_locks(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Detecta procesos que mantienen locks en bóvedas DuckDB."""
    _run_script("check_duckdb_lock_holders.py", [], dry_run=dry_run)


@app.command(
    "cleanup-default-tenant-schemas",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cleanup_default_tenant_schemas(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Limpia esquemas tenant-specific de default.duckdb."""
    _run_script("cleanup_default_duckdb_tenant_schemas.py", list(ctx.args), dry_run=dry_run)


@app.command("authorized-users", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def authorized_users(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Lista filas en main.authorized_users."""
    _run_script("check_authorized_users.py", list(ctx.args), dry_run=dry_run)
