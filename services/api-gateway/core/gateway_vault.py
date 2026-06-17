"""Bóveda DuckDB dedicada por gateway PM2 (multiplex)."""

from __future__ import annotations

from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved


def dedicated_gateway_vault_db_path() -> str | None:
    """
    Si este proceso es un gateway listado en api_gateways_pm2.json con rutas multiplex,
    esa DuckDB sustituye al vault activo del usuario (fly commands, manager, workers).
    """
    return dedicated_gateway_db_path_resolved()
