"""Comando down: apaga PM2, libera locks DuckDB y consola admin dev."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.stack_shutdown import run_stack_down

app = typer.Typer()


@app.callback(invoke_without_command=True)
def cmd_down(
    ctx: typer.Context,
    repo: Path | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    all_services: bool = typer.Option(
        False,
        "--all",
        help="Detener también Voice, MCP, Sensory, MLX, ComfyUI y admin spawn si están en PM2.",
    ),
    no_pm2: bool = typer.Option(False, "--no-pm2", help="No llamar pm2 stop (solo locks y admin dev)."),
    no_locks: bool = typer.Option(False, "--no-locks", help="No matar PIDs que bloqueen .duckdb."),
    no_admin: bool = typer.Option(False, "--no-admin", help="No detener pnpm dev en el puerto admin."),
    prepare_migrate: bool = typer.Option(
        False,
        "--prepare-migrate",
        help="Stop Gateway/Writer/Indexer/Heartbeat + liberar locks (para duckclaw-migrate).",
    ),
) -> None:
    """
    Apaga el stack local en un solo paso (paridad con ``duckops up``).

    1. ``pm2 stop`` Gateway + DB-Writer (y opcionalmente todo DuckClaw con --all)
    2. Libera locks en hub/vault DuckDB (``lsof`` + kill)
    3. Detiene la consola admin ``pnpm dev`` si escucha en :3001

    Útil antes de ``uv run duckclaw-migrate`` cuando migrate falla por lock.
    """
    if ctx.invoked_subcommand is not None:
        return
    if prepare_migrate:
        from duckops.stack_shutdown import prepare_duckdb_for_migrate

        code = prepare_duckdb_for_migrate(repo, print_fn=typer.echo)
        raise typer.Exit(code)
    code = run_stack_down(
        repo,
        all_services=all_services,
        stop_pm2=not no_pm2,
        release_locks=not no_locks,
        stop_admin=not no_admin,
        print_fn=typer.echo,
    )
    raise typer.Exit(code)
