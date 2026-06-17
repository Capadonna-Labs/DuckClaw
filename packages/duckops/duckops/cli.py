"""DuckClaw Operations CLI — Wizard, deploy y auditoría."""

from __future__ import annotations

from pathlib import Path

import typer

from duckops.commands import audit, bootstrap, comfyui, db, deploy, doctor, ingress, init, mcp, serve, smoke, stack, train, up

app = typer.Typer(
    name="duckops",
    help="DuckClaw Operations CLI — Wizard, deploy y auditoría Habeas Data.",
)

app.add_typer(
    up.app,
    name="up",
    help="Plug-and-play: prerequisitos, init, migrate, stack PM2 y consola admin.",
)
app.add_typer(
    bootstrap.app,
    name="bootstrap",
    help="Instala prerequisitos: uv, Redis, Node, PM2 y uv sync (macOS/Linux).",
)
app.add_typer(
    doctor.app,
    name="doctor",
    help="Diagnóstico local: Redis, migraciones, admin key y puerto gateway.",
)
app.add_typer(
    smoke.app,
    name="smoke",
    help="Smoke local: doctor + GET /health.",
)
app.add_typer(
    init.app,
    name="init",
    help="Sovereign Wizard v2.0 y setup inicial (ver duckops init --help).",
)
app.add_typer(serve.app, name="serve", help="Arranca el API Gateway o servidor LangGraph.")
app.add_typer(stack.app, name="stack", help="Estado y arranque del stack local DuckClaw.")
app.add_typer(deploy.app, name="deploy", help="Despliega DuckClaw como servicio (PM2, systemd, etc.).")
app.add_typer(ingress.app, name="ingress", help="Admin/Tailscale/Telegram ingress.")
app.add_typer(mcp.app, name="mcp", help="Operaciones MCP locales.")
app.add_typer(comfyui.app, name="comfyui", help="Operaciones del runtime ComfyUI.")
app.add_typer(db.app, name="db", help="Mantenimiento DuckDB/admin.")
app.add_typer(audit.app, name="audit", help="Auditoría Habeas Data (config, enmascaramiento).")
app.add_typer(
    train.app,
    name="train",
    help="SFT LoRA (MLX): train_sft o mlx_lm.lora --config; guardrail PM2 opcional.",
)


@app.command("mascot")
def cmd_mascot() -> None:
    """Demo Textual: pato mallard animado (IDLE / WALKING / WORKING)."""
    from duckops.sovereign.duck_mascot import run_mascot_demo

    raise typer.Exit(run_mascot_demo())
