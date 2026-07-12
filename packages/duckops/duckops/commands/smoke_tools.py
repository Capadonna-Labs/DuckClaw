"""Smoke playground tools: capabilities + turno read_sql."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from duckops.admin_bootstrap import admin_bootstrap_ready, is_admin_key_valid
from duckops.commands.doctor import _load_dotenv, _repo_root

app = typer.Typer()


def _emit(name: str, ok: bool, detail: str) -> bool:
    mark = "OK" if ok else "—"
    typer.echo(f"  {mark} {name} — {detail}")
    return ok


@app.callback(invoke_without_command=True)
def cmd_smoke_tools(
    ctx: typer.Context,
    repo: str | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    worker_id: str | None = typer.Option(None, "--worker", help="Worker id (default: del playground config)."),
    gateway_port: int | None = typer.Option(None, "--port", help="Puerto gateway (default: resolve_gateway_port)."),
) -> None:
    """Login + capabilities + chat que fuerza read_sql (prueba de tools en playground)."""
    if ctx.invoked_subcommand is not None:
        return

    root = Path(repo).resolve() if repo else _repo_root()
    _load_dotenv(root)

    from duckclaw.gateway_port import resolve_gateway_port

    port = int(gateway_port or resolve_gateway_port(root))
    admin_email = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    admin_pass = (os.environ.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    admin_key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()

    if not is_admin_key_valid(admin_key) or not admin_bootstrap_ready(admin_email, admin_pass, admin_key):
        typer.secho(
            "Configura DUCKCLAW_ADMIN_API_KEY, DUCKCLAW_ADMIN_EMAIL y DUCKCLAW_ADMIN_PASSWORD en .env",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    from duckops.playground_tools_smoke import run_playground_tools_smoke

    typer.echo("DuckClaw smoke tools (playground)")
    all_ok = True
    for row in run_playground_tools_smoke(
        base_url=f"http://127.0.0.1:{port}",
        admin_email=admin_email,
        admin_password=admin_pass,
        admin_api_key=admin_key,
        worker_id=worker_id,
    ):
        if not _emit(row.name, row.ok, row.detail):
            all_ok = False

    if not all_ok:
        typer.secho("Smoke tools falló.", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.secho("Smoke tools OK.", fg=typer.colors.GREEN)
