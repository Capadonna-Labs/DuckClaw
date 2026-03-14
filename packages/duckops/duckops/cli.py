import sys
import os
import subprocess
import click
from pathlib import Path

@click.group()
def cli():
    """DuckClaw Operations CLI - Cross-platform (Win/Lin/Mac)"""
    pass

@cli.command()
@click.option("--port", default=8000, help="Port to run the API gateway")
def serve(port):
    """Start the DuckClaw API Gateway (microservicio services/api-gateway)"""
    click.echo(f"Starting API Gateway on port {port}...")
    try:
        repo_root = Path(__file__).resolve().parents[4]
        app_dir = repo_root / "services" / "api-gateway"
        subprocess.run(
            ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port), "--app-dir", str(app_dir)],
            check=True,
            cwd=str(repo_root),
        )
    except Exception as e:
        click.echo(f"Error starting server: {e}")

@cli.command()
@click.option("--name", default="DuckClaw", help="Name of the service")
def status(name):
    """Show status of DuckClaw services (PM2 or Docker)"""
    # Try PM2 first
    try:
        subprocess.run(["pm2", "status", name], check=False)
    except FileNotFoundError:
        # Fallback to docker
        click.echo("PM2 not found. Checking Docker containers...")
        subprocess.run(["docker", "ps", "--filter", f"name={name}"], check=False)

@cli.command()
def setup():
    """Run the interactive setup wizard (Cross-platform)"""
    # Logic from scripts/duckclaw_setup_wizard.py would be ported here
    click.echo("Running setup wizard...")
    # ... implementation ...

def _entrypoint():
    cli()

if __name__ == "__main__":
    _entrypoint()
