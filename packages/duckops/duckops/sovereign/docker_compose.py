"""docker-compose.override.yml mínimo (spec §5)."""

from __future__ import annotations

from pathlib import Path

from duckops.sovereign.atomic import atomic_write

COMPOSE_OVERRIDE_TEMPLATE = """# Generado por duckops sovereign — Redis local para DuckClaw.
# Amplía con tu servicio gateway según tu imagen o bind-mount al repo.
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
"""


def write_compose_override(repo_root: Path) -> Path:
    path = repo_root / "docker-compose.override.yml"
    atomic_write(path, COMPOSE_OVERRIDE_TEMPLATE.strip() + "\n")
    return path
