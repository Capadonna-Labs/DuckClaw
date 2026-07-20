"""Comando init (deprecado): delega en configure."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.commands.configure import run_configure

app = typer.Typer()


@app.callback(invoke_without_command=True)
def cmd_init(
    ctx: typer.Context,
    tenant_id: str = typer.Argument(
        default="default",
        help="Reservado (compat).",
        hidden=True,
    ),
    repo: Path | None = typer.Option(
        None,
        "--repo",
        "-C",
        help="Raíz del monorepo DuckClaw (por defecto: cwd o ancestro).",
    ),
    chat: bool = typer.Option(
        False,
        "--chat",
        help="Abre el chat TUI con agentes (playground admin) sin ejecutar el wizard completo.",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        help="Wizard completo en CLI (Telegram, Tailscale). Por defecto: rápido + consola admin.",
    ),
    bootstrap: bool = typer.Option(
        True,
        "--bootstrap/--no-bootstrap",
        help="Verifica/instala uv, Redis, Node y PM2 antes del wizard.",
    ),
    yes: bool = typer.Option(
        True,
        "--yes/--no-yes",
        help="Instalar paquetes del sistema (brew/apt) si faltan. Usa --no-yes para solo comprobar.",
    ),
) -> None:
    """[Deprecado] Usa ``duckops up`` o ``duckops configure``."""
    if ctx.invoked_subcommand is not None:
        return

    typer.secho(
        "init está deprecado; usa duckops up o duckops configure",
        fg=typer.colors.YELLOW,
    )

    run_configure(
        tenant_id=tenant_id,
        repo=repo,
        chat=chat,
        manual=manual,
        bootstrap=bootstrap,
        yes=yes,
    )
