"""DuckClaw Operations CLI — Wizard, deploy y auditoría."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.commands import audit, deploy, init, serve, train

app = typer.Typer(
    name="duckops",
    help="DuckClaw Operations CLI — Wizard, deploy y auditoría Habeas Data.",
)

app.add_typer(
    init.app,
    name="init",
    help="Sovereign Wizard v2.0 y setup inicial (ver duckops init --help).",
)
app.add_typer(serve.app, name="serve", help="Arranca el API Gateway o servidor LangGraph.")
app.add_typer(deploy.app, name="deploy", help="Despliega DuckClaw como servicio (PM2, systemd, etc.).")
app.add_typer(audit.app, name="audit", help="Auditoría Habeas Data (config, enmascaramiento).")
app.add_typer(
    train.app,
    name="train",
    help="SFT LoRA (MLX): train_sft o mlx_lm.lora --config; guardrail PM2 opcional.",
)
