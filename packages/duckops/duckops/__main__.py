"""Ejecuta el CLI vía `python -m duckops` si falta el script en `.venv/bin` (p. ej. tras un sync incompleto)."""

from duckops.cli import app

if __name__ == "__main__":
    app()
