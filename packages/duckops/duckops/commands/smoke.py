"""Smoke test local: doctor + probe HTTP /health."""

from __future__ import annotations

import typer

app = typer.Typer()


@app.callback(invoke_without_command=True)
def cmd_smoke(
    ctx: typer.Context,
    repo: str | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
) -> None:
    """Diagnóstico + probe GET /health (alias de duckops doctor --smoke)."""
    if ctx.invoked_subcommand is not None:
        return
    from pathlib import Path

    from duckops.commands.doctor import cmd_doctor

    root = Path(repo).resolve() if repo else None
    try:
        cmd_doctor(ctx, repo=root, smoke=True)
    except typer.Exit as exc:
        raise typer.Exit(exc.exit_code) from exc
