"""Comando up: plug-and-play — prerequisitos, init, migrate, stack y consola admin."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
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


def _backup_dir(repo: Path) -> Path:
    return repo / ".duckops" / "migrate-backups"


def _backup_manifest_path(repo: Path) -> Path:
    return _backup_dir(repo) / "last_backup.json"


def _resolve_gateway_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    return (get_gateway_db_path() or "").strip()


def _create_gateway_db_backup(repo: Path, print_fn) -> tuple[str, str]:
    db_path = _resolve_gateway_db_path()
    if not db_path:
        print_fn("No se resolvió DUCKDB del gateway; backup de migración omitido.")
        return "", ""
    source = Path(db_path).expanduser()
    if not source.is_file():
        print_fn(f"Gateway DB no existe aún ({source}); backup omitido.")
        return str(source), ""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = _backup_dir(repo)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"{source.stem}.pre_migrate_{stamp}.duckdb.bak"
    shutil.copy2(source, backup_path)
    _backup_manifest_path(repo).write_text(
        json.dumps(
            {
                "db_path": str(source.resolve()),
                "backup_path": str(backup_path.resolve()),
                "created_at": stamp,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print_fn(f"Backup migración: {backup_path}")
    return str(source.resolve()), str(backup_path.resolve())


def _rollback_gateway_db(repo: Path, print_fn) -> bool:
    manifest = _backup_manifest_path(repo)
    if not manifest.is_file():
        print_fn("No existe backup registrado para rollback.")
        return False
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        print_fn("Manifest de backup inválido; rollback cancelado.")
        return False
    db_path = str(payload.get("db_path") or "").strip()
    backup_path = str(payload.get("backup_path") or "").strip()
    if not db_path or not backup_path:
        print_fn("Manifest incompleto; rollback cancelado.")
        return False
    source = Path(backup_path).expanduser()
    target = Path(db_path).expanduser()
    if not source.is_file():
        print_fn(f"Backup no encontrado: {source}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print_fn(f"Rollback aplicado: {source} -> {target}")
    return True


def _post_migrate_catalog_hint(print_fn) -> None:
    """One-line hint when catalog worker prompts are missing after migrate."""
    try:
        from duckclaw.gateway_db import get_gateway_db_path
        import duckdb

        from duckops.policy_health import check_catalog_worker_system_prompts, check_framework_prompt_policies

        db_path = (get_gateway_db_path() or "").strip()
        if not db_path:
            return
        con = duckdb.connect(db_path, read_only=True)
        try:
            catalog = check_catalog_worker_system_prompts(con)
            framework = check_framework_prompt_policies(con)
        finally:
            con.close()
    except Exception:
        return

    if not catalog.ok:
        print_fn(
            "  hint: faltan prompts por agente — en admin → Prompt policies → Sync catálogo "
            f"({catalog.summary()})."
        )
    elif framework.degraded:
        print_fn(
            "  hint: policies framework en modo degradado — Restaurar defaults o Sync catálogo en admin."
        )


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
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fallar si faltan policies framework críticas (degradado solo avisa).",
    ),
    migrate: bool = typer.Option(
        True,
        "--migrate/--no-migrate",
        help="Aplicar migraciones DuckDB durante up (default: sí).",
    ),
    rollback_migration: bool = typer.Option(
        False,
        "--rollback-migration",
        help="Restaurar último backup pre-migración y salir.",
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
        typer.secho(
            "Instalacion abortada en paso 1/6 (prerequisitos del sistema). "
            "Lee el bloque FALLO EN PREREQUISITOS arriba.",
            fg=typer.colors.RED,
            err=True,
        )
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
            "Falta configuración. Quita --skip-init o ejecuta: uv run duckops up",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    else:
        typer.echo("Configuración existente — wizard omitido.")
    typer.echo("")

    _load_dotenv(root)

    if rollback_migration:
        typer.secho("[ROLLBACK] Restaurando último backup de migración", fg=typer.colors.BLUE, bold=True)
        if _rollback_gateway_db(root, typer.echo):
            typer.secho("Rollback completado.", fg=typer.colors.GREEN)
            raise typer.Exit(0)
        typer.secho("Rollback no aplicado.", fg=typer.colors.RED)
        raise typer.Exit(1)

    # —— 3/6 Migrate ——
    typer.secho("[3/6] Migraciones DuckDB", fg=typer.colors.BLUE, bold=True)
    if migrate:
        _db_path, backup = _create_gateway_db_backup(root, typer.echo)
        if not _run_migrate(root, typer.echo):
            typer.secho("migrate falló; intentando rollback automático…", fg=typer.colors.YELLOW)
            rolled_back = _rollback_gateway_db(root, typer.echo) if backup else False
            detail = "rollback aplicado" if rolled_back else "rollback no disponible"
            typer.secho(f"migrate falló ({detail}).", fg=typer.colors.RED)
            raise typer.Exit(1)
        _post_migrate_catalog_hint(typer.echo)
    else:
        typer.secho("Migraciones omitidas (--no-migrate).", fg=typer.colors.YELLOW)
    typer.echo("")

    # —— 4/6 Stack ——
    typer.secho("[4/6] Gateway + DB-Writer (PM2)", fg=typer.colors.BLUE, bold=True)
    if platform.system() == "Windows":
        from duckops.prerequisites import augment_path_for_windows_tools

        augment_path_for_windows_tools()
    if not _run_serve_stack(root, typer.echo):
        typer.secho("serve falló.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo("")

    # —— 5/6 Smoke ——
    typer.secho("[5/6] Smoke /health", fg=typer.colors.BLUE, bold=True)
    if not _run_smoke(root, typer.echo):
        typer.secho("Gateway no respondió; espera unos segundos y: uv run duckops smoke", fg=typer.colors.YELLOW)
    from duckops.policy_health import run_framework_policy_preflight

    if not run_framework_policy_preflight(root, print_fn=typer.echo, strict=strict):
        typer.secho(
            "Policies framework críticas ausentes; ejecuta duckclaw-migrate o usa --strict solo en CI.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
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
