"""Comando doctor: diagnóstico rápido del entorno local (solo lectura)."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

import typer

from duckops.admin_bootstrap import (
    admin_bootstrap_ready,
    is_admin_key_valid,
)

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _load_dotenv(repo: Path) -> None:
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(repo / ".env")
    except ImportError:
        pass


def _emit(label: str, ok: bool, detail: str) -> bool:
    mark = typer.style("OK", fg=typer.colors.GREEN) if ok else typer.style("—", fg=typer.colors.YELLOW)
    typer.echo(f"  {mark} {label} — {detail}")
    return ok


@app.callback(invoke_without_command=True)
def cmd_doctor(
    ctx: typer.Context,
    repo: Path | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    smoke: bool = typer.Option(False, "--smoke", help="Además, probe GET /health si el gateway escucha."),
    bootstrap: bool = typer.Option(
        False,
        "--bootstrap",
        help="Instala prerequisitos faltantes (uv, Redis, Node, PM2) y ejecuta uv sync.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Con --bootstrap: instalar sin pedir confirmación (brew/apt).",
    ),
) -> None:
    """Comprueba Redis, migraciones, admin key y puerto gateway."""
    if ctx.invoked_subcommand is not None:
        return

    root = (repo or _repo_root()).resolve()

    if bootstrap:
        from duckops.prerequisites import ensure_development_prerequisites, platform_label

        typer.secho(f"DuckClaw bootstrap ({platform_label()})", fg=typer.colors.CYAN)
        if not ensure_development_prerequisites(
            root,
            install=True,
            assume_yes=yes,
            sync_python=True,
            print_fn=typer.echo,
        ):
            raise typer.Exit(1)
        typer.echo("")

    _load_dotenv(root)
    typer.secho("DuckClaw doctor", fg=typer.colors.CYAN)

    critical_ok = True

    try:
        from duckops.prerequisites import check_all

        for tool in check_all():
            is_critical = tool.name == "Redis"
            if not _emit(
                tool.name,
                tool.ok,
                f"{tool.version} · {tool.detail}" if tool.version else tool.detail,
            ):
                if is_critical:
                    critical_ok = False
    except Exception as exc:
        if not _emit("Prerequisitos", False, str(exc)[:160]):
            critical_ok = False

    db_path = ""
    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.schema_migrations import verify_schema_integrity

        db_path = (get_gateway_db_path() or "").strip()
        if not db_path:
            _emit("Migraciones", True, "sin ruta hub (ejecuta duckops init)")
        else:
            ok_schema, msg_schema = verify_schema_integrity(db_path)
            if not _emit(
                "Migraciones",
                ok_schema,
                f"{db_path}" if ok_schema else f"{db_path}: {msg_schema}",
            ):
                critical_ok = False
    except Exception as exc:
        if not _emit("Migraciones", False, str(exc)[:160]):
            critical_ok = False

    admin_key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    key_ok = is_admin_key_valid(admin_key)
    _emit(
        "Admin API key",
        key_ok,
        "configurada" if key_ok else "falta o placeholder (duckops init)",
    )

    admin_email = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    admin_pass = (os.environ.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    seed_ok = admin_bootstrap_ready(admin_email, admin_pass, admin_key)
    _emit(
        "Admin login seed",
        seed_ok,
        admin_email if seed_ok else "DUCKCLAW_ADMIN_EMAIL/PASSWORD incompletos o placeholder",
    )

    gateway_listening = False
    gateway_port = 8000
    try:
        from duckclaw.gateway_port import resolve_gateway_port
        from duckops.sovereign.validate import is_port_in_use

        gateway_port = int(resolve_gateway_port(root))
        gateway_listening = is_port_in_use("127.0.0.1", gateway_port)
        _emit(
            "Gateway puerto",
            True,
            f":{gateway_port} {'en escucha' if gateway_listening else 'libre (duckops serve --gateway --pm2)'}",
        )
    except Exception as exc:
        _emit("Gateway puerto", False, str(exc)[:160])

    if smoke:
        smoke_ok = False
        if gateway_listening:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{gateway_port}/health",
                    timeout=3.0,
                ) as response:
                    body = response.read(200).decode("utf-8", errors="replace")
                    smoke_ok = 200 <= int(response.status) < 300
                detail = f"HTTP {response.status}" + (f" · {body[:80]}" if body else "")
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                detail = str(exc)[:120]
        else:
            detail = "gateway no escucha — ejecuta: uv run duckops serve --gateway --pm2 --stack"
        if not _emit("Smoke /health", smoke_ok, detail):
            critical_ok = False

    if not critical_ok:
        typer.secho(
            "Corrige lo anterior. Instala prerequisitos: uv run duckops bootstrap --yes",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    typer.secho("Listo para init/serve o stack ya operativo.", fg=typer.colors.GREEN)
