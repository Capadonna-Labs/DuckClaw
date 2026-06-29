"""Stack operations: local launcher/status for DuckClaw services."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import typer


app = typer.Typer()

GATEWAY_NAME = "DuckClaw-Gateway"
DB_WRITER_NAME = "DuckClaw-DB-Writer"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    from duckclaw.ops.providers.pm2 import pm2_argv

    if argv and argv[0] == "pm2":
        argv = pm2_argv(*argv[1:])
    try:
        return subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        cmd = argv[0] if argv else "comando"
        typer.echo(
            f"No se encontró '{cmd}' en PATH. "
            "Instala PM2: npm install -g pm2 (o: uv run duckops up / duckops prerequisites). "
            "Sin PM2: uv run duckops serve --gateway en otra terminal.",
            err=True,
        )
        raise typer.Exit(127) from exc


def _resolve_provider(provider: str) -> str:
    selected = (provider or "auto").strip().lower()
    if selected == "auto":
        return "pm2"
    return selected


def _pm2_processes() -> list[dict[str, Any]]:
    proc = _run(["pm2", "jlist"])
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _pm2_status_by_name(name: str) -> str:
    for item in _pm2_processes():
        if str(item.get("name") or "") != name:
            continue
        env = item.get("pm2_env") if isinstance(item.get("pm2_env"), dict) else {}
        return str(env.get("status") or "unknown")
    return "missing"


def _gateway_health_ok(host: str = "127.0.0.1", port: int = 8000, timeout_seconds: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout_seconds) as response:
            response.read()
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _wait_for_gateway_health(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while time.monotonic() <= deadline:
        if _gateway_health_ok(host=host, port=port):
            return True
        time.sleep(0.5)
    return False


def _service_report(*, provider: str, host: str, port: int) -> dict[str, Any]:
    gateway_status = _pm2_status_by_name(GATEWAY_NAME) if provider == "pm2" else "unknown"
    db_writer_status = _pm2_status_by_name(DB_WRITER_NAME) if provider == "pm2" else "unknown"
    gateway_health = _gateway_health_ok(host=host, port=port) if gateway_status == "online" else False
    services = {
        GATEWAY_NAME: {"status": gateway_status, "health_ok": gateway_health},
        DB_WRITER_NAME: {"status": db_writer_status},
    }
    all_ok = gateway_status == "online" and gateway_health and db_writer_status == "online"
    return {"provider": provider, "host": host, "port": port, "services": services, "all_ok": all_ok}


def _print_status(report: dict[str, Any]) -> None:
    typer.echo(f"Proveedor: {report['provider']}")
    typer.echo(f"Gateway: http://{report['host']}:{report['port']}")
    for name, info in report["services"].items():
        health = ""
        if "health_ok" in info:
            health = f" health={'ok' if info['health_ok'] else 'pending'}"
        typer.echo(f"- {name}: {info['status']}{health}")


@app.command("status")
def status(
    provider: str = typer.Option("auto", "--provider", help="Proveedor: auto, pm2 o systemd."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host local del Gateway."),
    port: int = typer.Option(8000, "--port", help="Puerto local del Gateway."),
    as_json: bool = typer.Option(False, "--json", help="Imprime salida JSON para automatización."),
) -> None:
    """Muestra estado del stack sin modificar el sistema."""
    selected = _resolve_provider(provider)
    if selected != "pm2":
        raise typer.BadParameter("Por ahora stack status soporta provider=pm2 o auto.")
    report = _service_report(provider=selected, host=host, port=port)
    if as_json:
        typer.echo(json.dumps(report, sort_keys=True))
        return
    _print_status(report)
    if not report["all_ok"]:
        raise typer.Exit(1)


def _pm2_start(ecosystem_path: Path, service_name: str) -> bool:
    before = _pm2_status_by_name(service_name)
    proc = _run(["pm2", "start", str(ecosystem_path), "--only", service_name, "--update-env"])
    if proc.returncode != 0:
        typer.echo(proc.stderr or proc.stdout, err=True)
        raise typer.Exit(proc.returncode)
    after = _pm2_status_by_name(service_name)
    return before != "online" or after != before


@app.command("up")
def up(
    provider: str = typer.Option("auto", "--provider", help="Proveedor: auto, pm2 o systemd."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host local del Gateway."),
    port: int = typer.Option(8000, "--port", help="Puerto local del Gateway."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Espera a que /health responda OK."),
    timeout_seconds: float = typer.Option(30.0, "--timeout", help="Tiempo máximo de espera de Gateway."),
) -> None:
    """Arranca servicios locales DuckClaw con el proveedor operativo."""
    selected = _resolve_provider(provider)
    if selected != "pm2":
        raise typer.BadParameter("Por ahora stack up soporta provider=pm2 o auto.")

    root = _repo_root()
    api_ecosystem = root / "config" / "ecosystem.api.config.cjs"
    db_writer_ecosystem = root / "config" / "ecosystem.db-writer.config.cjs"
    if not api_ecosystem.is_file():
        typer.echo(f"No existe {api_ecosystem}", err=True)
        raise typer.Exit(1)

    changed = _pm2_start(api_ecosystem, GATEWAY_NAME)
    if db_writer_ecosystem.is_file():
        changed = _pm2_start(db_writer_ecosystem, DB_WRITER_NAME) or changed

    if changed:
        proc = _run(["pm2", "save"])
        if proc.returncode != 0:
            typer.echo(proc.stderr or proc.stdout, err=True)
            raise typer.Exit(proc.returncode)

    if wait and not _wait_for_gateway_health(host, port, timeout_seconds):
        typer.echo(f"Gateway no respondió OK en http://{host}:{port}/health", err=True)
        raise typer.Exit(1)

    _print_status(_service_report(provider=selected, host=host, port=port))


@app.command("down")
def stack_down(
    all_services: bool = typer.Option(
        False,
        "--all",
        help="Detener también Voice, MCP, Sensory y demás procesos DuckClaw en PM2.",
    ),
) -> None:
    """Alias de ``duckops down`` — apaga stack local y libera locks DuckDB."""
    from duckops.stack_shutdown import run_stack_down

    code = run_stack_down(all_services=all_services, print_fn=typer.echo)
    raise typer.Exit(code)

