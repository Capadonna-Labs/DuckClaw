"""Comando configure: Sovereign Wizard v2.0."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    """Raíz del monorepo (packages/duckops/duckops/commands -> ../../../../)."""
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def run_configure(
    *,
    tenant_id: str = "default",
    repo: Path | None = None,
    chat: bool = False,
    manual: bool = False,
    bootstrap: bool = True,
    yes: bool = True,
) -> None:
    """Ejecuta el wizard de configuración Sovereign v2.0."""
    del tenant_id  # reserved for future multi-tenant configure UX
    repo_path = repo.resolve() if repo is not None else None
    base = repo_path if repo_path is not None else _repo_root()

    if bootstrap:
        from duckops.prerequisites import ensure_development_prerequisites, platform_label

        typer.secho(f"Prerequisitos ({platform_label()})", fg=typer.colors.CYAN)
        if not ensure_development_prerequisites(
            base,
            install=True,
            assume_yes=yes,
            sync_python=True,
            print_fn=typer.echo,
        ):
            typer.secho(
                "Bootstrap falló. Prueba: uv run duckops bootstrap --yes",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        typer.echo("")

    from duckops.sovereign.runner import run_sovereign_chat, run_sovereign_wizard

    if chat:
        raise typer.Exit(run_sovereign_chat(repo_path))
    raise typer.Exit(run_sovereign_wizard(repo_path, manual=manual))


@app.callback(invoke_without_command=True)
def cmd_configure(
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
        help="Carpeta del proyecto DuckClaw (por defecto: donde estás parado).",
    ),
    chat: bool = typer.Option(
        False,
        "--chat",
        help="Probar el chat en terminal, sin abrir la consola web.",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        help="Configuración avanzada: Telegram, Tailscale y más opciones.",
    ),
    bootstrap: bool = typer.Option(
        True,
        "--bootstrap/--no-bootstrap",
        help="Comprobar e instalar lo necesario (Redis, Node, etc.) antes de configurar.",
    ),
    yes: bool = typer.Option(
        True,
        "--yes/--no-yes",
        help="Instalar automáticamente lo que falte en tu Mac o Linux.",
    ),
) -> None:
    """Vuelve a configurar DuckClaw (cuentas, claves, servicios). Para la primera vez usa duckops up."""
    if ctx.invoked_subcommand is not None:
        return

    run_configure(
        tenant_id=tenant_id,
        repo=repo,
        chat=chat,
        manual=manual,
        bootstrap=bootstrap,
        yes=yes,
    )
