"""Comando up: plug-and-play — prerequisitos, init, migrate, stack y consola admin."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

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


def _run_migrate(repo: Path, print_fn) -> bool:
    uv = _which_uv()
    if not uv:
        print_fn("uv no encontrado para migrar.")
        return False
    print_fn("duckclaw-migrate …")
    proc = subprocess.run(
        [uv, "run", "duckclaw-migrate"],
        cwd=str(repo),
        check=False,
    )
    return proc.returncode == 0


def _which_uv() -> str | None:
    import shutil

    return shutil.which("uv")


def _run_serve_stack(repo: Path, print_fn) -> bool:
    """Gateway + DB-Writer vía PM2 (misma lógica que serve --gateway --pm2 --stack)."""
    import duckops.commands.serve as serve_mod

    class _Ctx:
        invoked_subcommand = None

    try:
        serve_mod.cmd_serve(
            _Ctx(),
            host="0.0.0.0",
            port=None,
            pm2=True,
            gateway=True,
            stack=True,
            name=None,
            delete_pm2_name=None,
            gateway_db_path=None,
            reload=False,
        )
        return True
    except typer.Exit as exc:
        return int(exc.exit_code) == 0
    except SystemExit as exc:
        code = exc.code
        return code in (0, None)


def _run_smoke(repo: Path, print_fn) -> bool:
    import duckops.commands.doctor as doctor_mod

    class _Ctx:
        invoked_subcommand = None

    try:
        doctor_mod.cmd_doctor(_Ctx(), repo=repo, smoke=True, bootstrap=False, yes=False)
        return True
    except typer.Exit as exc:
        print_fn(f"Smoke falló (código {exc.exit_code}).")
        return False


@app.callback(invoke_without_command=True)
def cmd_up(
    ctx: typer.Context,
    repo: Path | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    yes: bool = typer.Option(
        True,
        "--yes/--no-yes",
        help="Instalar Redis, Node, PM2 automáticamente si faltan.",
    ),
    skip_init: bool = typer.Option(
        False,
        "--skip-init",
        help="No abrir el wizard aunque falte configuración.",
    ),
    skip_admin: bool = typer.Option(
        False,
        "--skip-admin",
        help="No arrancar la consola Next.js.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="No abrir el navegador al final.",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        help="Wizard Sovereign completo (Telegram, Tailscale) si hace falta init.",
    ),
    ui: str | None = typer.Option(
        None,
        "--ui",
        help="Sin menú interactivo: tui | web | none.",
    ),
    no_prompt: bool = typer.Option(
        False,
        "--no-prompt",
        help="No preguntar al final; salir tras el resumen (CI/scripts).",
    ),
) -> None:
    """
    Un solo comando para el día 0:

    1. Prerequisitos (uv, Redis, Node, PM2) + uv sync
    2. Wizard Sovereign si falta configuración
    3. Migraciones DuckDB
    4. Gateway + DB-Writer (PM2)
    5. Smoke /health
    6. Elección: chat TUI o consola web (el comando no termina hasta que salgas)
    """
    if ctx.invoked_subcommand is not None:
        return

    root = (repo or _repo_root()).resolve()
    typer.secho("🦆 DuckClaw up", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"Repo: {root}\n")

    from duckops.admin_dev_server import admin_login_url, resolve_admin_port, wait_admin_http
    from duckops.post_up import run_post_up_loop
    from duckops.prerequisites import ensure_development_prerequisites, platform_label
    from duckops.stack_readiness import admin_credentials_hint, needs_wizard_init

    # —— 1/6 Prerequisitos ——
    typer.secho("[1/6] Prerequisitos del sistema", fg=typer.colors.BLUE, bold=True)
    if not ensure_development_prerequisites(
        root,
        install=True,
        assume_yes=yes,
        sync_python=True,
        print_fn=typer.echo,
    ):
        raise typer.Exit(1)
    typer.echo("")

    # —— 2/6 Init ——
    typer.secho("[2/6] Configuración inicial", fg=typer.colors.BLUE, bold=True)
    if needs_wizard_init(root) and not skip_init:
        typer.echo("Primera vez o configuración incompleta → abriendo wizard TUI…")
        from duckops.sovereign.runner import run_sovereign_wizard

        code = run_sovereign_wizard(root, manual=manual)
        if code != 0:
            typer.secho("Wizard cancelado o falló.", fg=typer.colors.RED)
            raise typer.Exit(code)
    elif needs_wizard_init(root):
        typer.secho(
            "Falta configuración. Quita --skip-init o ejecuta: uv run duckops init",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    else:
        typer.echo("Configuración existente — wizard omitido.")
    typer.echo("")

    _load_dotenv(root)

    # —— 3/6 Migrate ——
    typer.secho("[3/6] Migraciones DuckDB", fg=typer.colors.BLUE, bold=True)
    if not _run_migrate(root, typer.echo):
        typer.secho("migrate falló; revisa el log.", fg=typer.colors.YELLOW)
    typer.echo("")

    # —— 4/6 Stack ——
    typer.secho("[4/6] Gateway + DB-Writer (PM2)", fg=typer.colors.BLUE, bold=True)
    if not _run_serve_stack(root, typer.echo):
        typer.secho("serve falló.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo("")

    # —— 5/6 Smoke ——
    typer.secho("[5/6] Smoke /health", fg=typer.colors.BLUE, bold=True)
    if not _run_smoke(root, typer.echo):
        typer.secho("Gateway no respondió; espera unos segundos y: uv run duckops smoke", fg=typer.colors.YELLOW)
    typer.echo("")

    # —— 6/6 Consola admin (estado) + sesión interactiva ——
    if skip_admin:
        typer.secho("Consola web omitida (--skip-admin).", fg=typer.colors.YELLOW)
    else:
        typer.secho("[6/6] Consola admin", fg=typer.colors.BLUE, bold=True)
        port = resolve_admin_port(root)
        if wait_admin_http(port, timeout_seconds=2.0):
            typer.echo(f"Consola admin ya escucha en :{port}")
        else:
            typer.echo(
                f"Consola admin no está en :{port} — se arrancará si eliges la opción web."
            )
        typer.echo("")

    email, password = admin_credentials_hint(root)
    typer.secho("\n✓ DuckClaw listo", fg=typer.colors.GREEN, bold=True)
    if not skip_admin:
        typer.echo(f"  Consola: {admin_login_url(root)}")
    if email:
        typer.echo(f"  Usuario: {email}")
    if password:
        typer.echo("  Contraseña: (ver DUCKCLAW_ADMIN_PASSWORD en .env)")
    typer.echo("  Tras login web → Playground (chat con agentes)")
    typer.echo(f"  Plataforma: {platform_label()}")

    code = run_post_up_loop(
        root,
        skip_admin=skip_admin,
        no_browser=no_browser,
        ui=ui,
        no_prompt=no_prompt,
        print_fn=typer.echo,
    )
    raise typer.Exit(code)
