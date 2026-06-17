"""Bootstrap: instala prerequisitos del stack (uv, Redis, Node, PM2) y uv sync."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.prerequisites import ensure_development_prerequisites, platform_label

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@app.callback(invoke_without_command=True)
def cmd_bootstrap(
    ctx: typer.Context,
    repo: Path | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Instalar paquetes del sistema sin confirmación interactiva (brew/apt).",
    ),
    check_only: bool = typer.Option(
        False,
        "--check",
        help="Solo listar estado; no instalar ni uv sync.",
    ),
    no_sync: bool = typer.Option(
        False,
        "--no-sync",
        help="No ejecutar uv sync tras instalar.",
    ),
) -> None:
    """Verifica e instala uv, Redis, Node.js, npm y PM2 (macOS/Linux)."""
    if ctx.invoked_subcommand is not None:
        return

    root = (repo or _repo_root()).resolve()
    typer.secho(f"DuckClaw bootstrap ({platform_label()})", fg=typer.colors.CYAN)
    typer.echo(f"Repo: {root}")

    ok = ensure_development_prerequisites(
        root,
        install=not check_only,
        assume_yes=yes,
        sync_python=not check_only and not no_sync,
        print_fn=typer.echo,
    )
    if not ok:
        typer.secho(
            "Bootstrap incompleto. En Linux puede hacer falta sudo. "
            "Revisa mensajes arriba o instala manualmente.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    typer.secho(
        "Prerequisitos listos. Siguiente: uv run duckops init",
        fg=typer.colors.GREEN,
    )
