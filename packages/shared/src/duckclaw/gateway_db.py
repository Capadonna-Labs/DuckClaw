"""
Ruta y acceso a la BD del API Gateway (microservicio services/api-gateway).

Usado por duckclaw.graphs.graph_server, forge, workers y scripts cuando necesitan
la misma DuckDB que usa el Gateway. Resuelve desde DUCKCLAW_DB_PATH o DUCKDB_PATH.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_gateway_db_path() -> str:
    """
    Ruta del archivo DuckDB que usa el API Gateway (services/api-gateway).
    Resuelve DUCKCLAW_DB_PATH, luego DUCKDB_PATH; por defecto db/duckclaw.duckdb.
    No resuelve a ruta absoluta; el caller puede hacer Path(path).resolve() si necesita.
    """
    path = os.environ.get("DUCKCLAW_DB_PATH", "").strip()
    if path:
        return path
    return os.environ.get("DUCKDB_PATH", "db/duckclaw.duckdb").strip() or "db/duckclaw.duckdb"
