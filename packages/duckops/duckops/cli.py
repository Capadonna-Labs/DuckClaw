"""DuckClaw Operations CLI — Wizard, deploy y auditoría."""

from __future__ import annotations

import typer

from duckops.commands import audit, deploy, init, serve

app = typer.Typer(
    name="duckops",
    help="DuckClaw Operations CLI — Wizard, deploy y auditoría Habeas Data.",
)

app.add_typer(init.app, name="init", help="Inicializa tenant y ejecuta el wizard de configuración.")
app.add_typer(serve.app, name="serve", help="Arranca el API Gateway o servidor LangGraph.")
app.add_typer(deploy.app, name="deploy", help="Despliega DuckClaw como servicio (PM2, systemd, etc.).")
app.add_typer(audit.app, name="audit", help="Auditoría Habeas Data (config, enmascaramiento).")
