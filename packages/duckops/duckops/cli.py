"""DuckClaw Operations CLI — Wizard, deploy y auditoría."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.commands import audit, deploy, init, serve
from duckops.sovereign.runner import run_sovereign_wizard

app = typer.Typer(
    name="duckops",
    help="DuckClaw Operations CLI — Wizard, deploy y auditoría Habeas Data.",
)

app.add_typer(init.app, name="init", help="Inicializa tenant y ejecuta el wizard de configuración.")


@app.command("sovereign")
def sovereign_cmd(
    repo: Path | None = typer.Option(
        None,
        "--repo",
        "-C",
        help="Raíz del monorepo DuckClaw (por defecto: cwd o ancestro).",
    ),
) -> None:
    """Sovereign Wizard v2.0 — TUI con borrador hasta Review (spec v2.0)."""
    raise typer.Exit(run_sovereign_wizard(repo.resolve() if repo else None))
app.add_typer(serve.app, name="serve", help="Arranca el API Gateway o servidor LangGraph.")
app.add_typer(deploy.app, name="deploy", help="Despliega DuckClaw como servicio (PM2, systemd, etc.).")
app.add_typer(audit.app, name="audit", help="Auditoría Habeas Data (config, enmascaramiento).")
