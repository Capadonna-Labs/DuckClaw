"""Comando serve: arranca el API Gateway o LangGraph server."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    """Raíz del monorepo."""
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@app.callback(invoke_without_command=True)
def cmd_serve(
    ctx: typer.Context,
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host para escuchar."),
    port: int | None = typer.Option(
        None,
        "--port",
        "-p",
        help="Puerto (default: DUCKCLAW_GATEWAY_PORT en .env o api_gateways_pm2.json).",
    ),
    pm2: bool = typer.Option(False, "--pm2", help="Desplegar como servicio PM2."),
    gateway: bool = typer.Option(False, "--gateway", "-g", help="Usar microservicio services/api-gateway (Telegram, agentes)."),
    stack: bool = typer.Option(
        True,
        "--stack/--no-stack",
        help="Con --gateway --pm2: arranca DB-Writer y comprueba Redis antes.",
    ),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Nombre del servicio PM2 (default: DuckClaw-Gateway con --gateway, DuckClaw-API si no).",
    ),
    delete_pm2_name: str = typer.Option(
        None,
        "--delete-pm2-name",
        help="Con --pm2: elimina este proceso PM2 antes de arrancar (p. ej. al renombrar el Gateway).",
    ),
    gateway_db_path: str = typer.Option(
        None,
        "--gateway-db-path",
        help="Con --pm2 --gateway: fija DUCKCLAW_GATEWAY_DB_PATH y DUCKDB_PATH para este proceso; "
        "sustituye la ruta persistida en api_gateways_pm2.json para ese nombre PM2.",
    ),
    reload: bool = typer.Option(False, "--reload", help="Recargar al cambiar código (solo sin --pm2)."),
) -> None:
    """Arranca el API Gateway o el servidor LangGraph."""
    if ctx.invoked_subcommand is not None:
        return
    effective_name = name or ("DuckClaw-Gateway" if gateway else "DuckClaw-API")
    repo = _repo_root()
    try:
        from duckclaw.gateway_port import resolve_gateway_port
        from duckclaw.ops.manager import serve as serve_fn
    except ImportError as e:
        typer.echo(f"[red]No se pudo importar duckclaw.ops: {e}[/]", err=True)
        typer.echo("Instala el monorepo: uv sync")
        raise typer.Exit(1)

    effective_port = (
        int(port)
        if port is not None
        else resolve_gateway_port(repo, app_name=effective_name)
    )

    if gateway and pm2 and stack:
        try:
            from duckclaw.runtime_env import resolve_redis_url
            from duckops.sovereign.validate import redis_ping_url

            redis_url = resolve_redis_url()
            ok_redis, msg_redis = redis_ping_url(redis_url)
            if ok_redis:
                typer.secho(f"Redis OK — {msg_redis}", fg=typer.colors.GREEN)
            else:
                typer.secho(
                    f"Redis no responde ({msg_redis}). "
                    "Arranca Redis (docker compose, brew services) antes del stack.",
                    fg=typer.colors.YELLOW,
                )
        except Exception as exc:
            typer.secho(f"No se pudo comprobar Redis: {exc}", fg=typer.colors.YELLOW)

    code = serve_fn(
        host=host,
        port=effective_port,
        reload=reload,
        pm2=pm2,
        name=effective_name,
        cwd=str(repo),
        gateway=gateway,
        delete_pm2_name=(delete_pm2_name.strip() if delete_pm2_name else None),
        gateway_db_path=(gateway_db_path.strip() if gateway_db_path else None),
    )
    if code != 0:
        raise typer.Exit(code)

    if gateway and pm2 and stack:
        import duckops.commands.stack as stack_mod

        db_ecosystem = repo / "config" / "ecosystem.db-writer.config.cjs"
        if db_ecosystem.is_file():
            try:
                stack_mod._pm2_start(db_ecosystem, stack_mod.DB_WRITER_NAME)
                typer.secho("DB-Writer PM2 arrancado (DuckClaw-DB-Writer).", fg=typer.colors.GREEN)
            except typer.Exit:
                raise
            except Exception as exc:
                typer.secho(f"DB-Writer: {exc}", fg=typer.colors.YELLOW)
        else:
            typer.secho(
                f"No existe {db_ecosystem}; ejecuta duckops init o duckops stack up.",
                fg=typer.colors.YELLOW,
            )
        if stack_mod._wait_for_gateway_health("127.0.0.1", effective_port, 15.0):
            typer.secho(f"Gateway /health OK en :{effective_port}", fg=typer.colors.GREEN)
        else:
            typer.secho(
                f"Gateway aún no responde en :{effective_port}/health "
                "(puede tardar unos segundos).",
                fg=typer.colors.YELLOW,
            )
