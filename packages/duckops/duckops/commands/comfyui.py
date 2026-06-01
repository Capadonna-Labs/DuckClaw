"""ComfyUI runtime helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _load_root_dotenv() -> None:
    env_path = _repo_root() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, _, value = clean.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _parse_api_target(api_url: str) -> tuple[str, str]:
    target = api_url.removeprefix("http://").removeprefix("https://")
    host, sep, rest = target.partition(":")
    port = rest.split("/", 1)[0] if sep else "8188"
    return host or "127.0.0.1", port or "8188"


@app.command("start")
def start(
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra el comando sin ejecutarlo."),
) -> None:
    """Arranca ComfyUI en modo API HTTP para DuckClaw/PM2."""
    _load_root_dotenv()
    comfy_home = Path(os.environ.get("COMFYUI_HOME") or Path.home() / "ComfyUI").expanduser()
    api_url = os.environ.get("COMFYUI_API_URL") or "http://127.0.0.1:8188"
    listen_host, port = _parse_api_target(api_url)
    python_candidates = [
        os.environ.get("COMFYUI_PYTHON") or "",
        str(comfy_home / "venv" / "bin" / "python"),
        str(comfy_home / ".venv" / "bin" / "python"),
        sys.executable,
    ]
    python_bin = next((Path(p) for p in python_candidates if p and Path(p).exists()), None)
    argv = [
        str(python_bin or sys.executable),
        "main.py",
        "--listen",
        listen_host,
        "--port",
        port,
    ]
    if dry_run:
        typer.echo(f"dry-run: cd {comfy_home}")
        typer.echo("dry-run: " + " ".join(argv))
        return
    if not comfy_home.is_dir() or not (comfy_home / "main.py").is_file():
        typer.echo(f"ERROR: instalación ComfyUI incompleta: {comfy_home}", err=True)
        raise typer.Exit(1)
    health_url = f"{api_url.rstrip('/')}/system_stats"
    try:
        import urllib.request

        with urllib.request.urlopen(health_url, timeout=3):
            typer.echo(f"ComfyUI ya responde en {api_url}")
            return
    except Exception:
        pass
    subprocess.run(argv, cwd=comfy_home, check=False)
