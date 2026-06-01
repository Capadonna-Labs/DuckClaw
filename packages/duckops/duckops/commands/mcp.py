"""MCP operational helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

app = typer.Typer()
prefetch_app = typer.Typer()
app.add_typer(prefetch_app, name="prefetch", help="Precarga paquetes MCP locales.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@prefetch_app.command("reddit")
def prefetch_reddit(
    package: str = typer.Option("mcp-reddit", "--package", help="Paquete npm MCP Reddit."),
    version: str = typer.Option("1.1.8", "--version", help="Versión npm del paquete."),
    cache_dir: str = typer.Option("", "--cache-dir", help="Directorio cache; default .mcp-cache/reddit."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Muestra comandos sin ejecutarlos."),
) -> None:
    """Precarga mcp-reddit para evitar npx lento en cold start del gateway."""
    root = _repo_root()
    cache = Path(cache_dir or os.environ.get("DUCKCLAW_REDDIT_MCP_CACHE_DIR") or root / ".mcp-cache" / "reddit")
    argv = ["npm", "install", f"{package}@{version}", "--no-fund", "--no-audit"]
    if dry_run:
        typer.echo(f"dry-run: mkdir -p {cache}")
        typer.echo("dry-run: cd " + str(cache))
        typer.echo("dry-run: npm init -y # si falta package.json")
        typer.echo("dry-run: " + " ".join(argv))
        return
    cache.mkdir(parents=True, exist_ok=True)
    if not (cache / "package.json").is_file():
        subprocess.run(["npm", "init", "-y"], cwd=cache, check=True)
    subprocess.run(argv, cwd=cache, check=True)
    server = cache / "node_modules" / package / "dist" / "server.js"
    if not server.is_file():
        typer.echo(f"Error: no se encontró {server}", err=True)
        raise typer.Exit(1)
    typer.echo(f"OK: {server.resolve()}")
