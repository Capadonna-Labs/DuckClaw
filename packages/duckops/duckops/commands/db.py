"""DuckDB/admin maintenance commands."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import typer

from duckops.db_vault_ops import fresh_dev_platform, migrate_legacy_axis_vault
from duckops.paths import repo_root

app = typer.Typer()

_MODULE_BY_SCRIPT: dict[str, str] = {
    "bootstrap_dbs.py": "duckops.db_bootstrap",
    "check_duckdb_lock_holders.py": "duckops.db_locks",
    "check_authorized_users.py": "duckops.db_authorized_users",
    "cleanup_default_duckdb_tenant_schemas.py": "duckops.db_cleanup_tenant",
}


def _run_module(module_name: str, extra_args: list[str], *, dry_run: bool) -> None:
    if dry_run:
        typer.echo(f"dry-run: {module_name} {' '.join(extra_args)}")
        return
    mod = importlib.import_module(module_name)
    main = getattr(mod, "main", None)
    if not callable(main):
        raise typer.BadParameter(f"{module_name} no expone main()")
    old_argv = sys.argv
    sys.argv = [module_name.split(".")[-1], *extra_args]
    try:
        raise typer.Exit(int(main()))
    finally:
        sys.argv = old_argv


def _run_script(script_name: str, extra_args: list[str], *, dry_run: bool) -> None:
    module_name = _MODULE_BY_SCRIPT.get(script_name)
    if module_name is None:
        raise typer.BadParameter(f"script no mapeado: {script_name}")
    _run_module(module_name, extra_args, dry_run=dry_run)


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


@app.command("fresh-dev")
def fresh_dev(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el plan sin ejecutarlo."),
) -> None:
    """Bóveda default limpia: down, rm vault, migrate, stack deploy."""
    raise typer.Exit(fresh_dev_platform(dry_run=dry_run))


@app.command("migrate-legacy-axis")
def migrate_legacy_axis(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el plan sin ejecutarlo."),
) -> None:
    """Renombra axis.duckdb → duckclaw.duckdb y limpia .env legacy."""
    raise typer.Exit(migrate_legacy_axis_vault(dry_run=dry_run))
