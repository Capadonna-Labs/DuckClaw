"""Ingress operations: Tailscale admin serve and Telegram webhook utilities."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _run(argv: list[str], *, dry_run: bool, env: dict[str, str] | None = None) -> None:
    if dry_run:
        typer.echo("dry-run: " + " ".join(argv))
        return
    proc = subprocess.run(argv, cwd=_repo_root(), env=env, text=True, check=False)
    raise typer.Exit(proc.returncode)


def _python_script(script_name: str, args: list[str], *, dry_run: bool) -> None:
    script = _repo_root() / "scripts" / script_name
    argv = [sys.executable, str(script), *args]
    _run(argv, dry_run=dry_run)


@app.command("serve-admin")
def serve_admin(
    port: int = typer.Option(
        None,
        "--port",
        help="Puerto local de Next admin. Default: DUCKCLAW_ADMIN_PORT o 3000.",
    ),
    https_port: int = typer.Option(8443, "--https-port", help="Puerto HTTPS de Tailscale Serve."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Expone la consola admin en la tailnet vía Tailscale Serve."""
    admin_port = int(port or os.environ.get("DUCKCLAW_ADMIN_PORT") or 3000)
    argv = [
        "tailscale",
        "serve",
        "--bg",
        f"--https={https_port}",
        f"http://127.0.0.1:{admin_port}",
    ]
    _run(argv, dry_run=dry_run)


@app.command("restore-admin-serve")
def restore_admin_serve(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Detecta el puerto admin y re-aplica Tailscale Serve :8443."""
    _python_script("restore_tailscale_admin_serve.py", [], dry_run=dry_run)


@app.command("telegram-check")
def telegram_check(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Comprueba gateway local, Tailscale Funnel y entrega webhook Telegram."""
    _python_script("check_telegram_ingress.py", [], dry_run=dry_run)


@app.command("telegram-register-webhooks")
def telegram_register_webhooks(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Registra setWebhook para DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES compacto."""
    _python_script("register_webhooks.py", [], dry_run=dry_run)


@app.command("telegram-start")
def telegram_start(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Activa Tailscale/Funnel, registra webhooks y verifica ingress Telegram."""
    _python_script("start_telegram_ingress.py", [], dry_run=dry_run)
