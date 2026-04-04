"""
Resolución de la DuckDB dedicada por gateway PM2 (config/api_gateways_pm2.json).

Usado por el API Gateway (vault/fly) y por comandos fly (/vault) para no mostrar
finanzdb1 del registry cuando el proceso es p. ej. SIATA-Gateway o BI-Analyst-Gateway.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_NAMES_CACHE: frozenset[str] | None = None


def _repo_root() -> Path:
    env = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for i in range(3, 8):
        try:
            cand = here.parents[i]
            if (cand / "config" / "api_gateways_pm2.json").is_file():
                return cand
        except IndexError:
            break
    return Path.cwd()


def clear_pm2_gateway_db_cache() -> None:
    """Tests o recarga de config."""
    global _NAMES_CACHE
    _NAMES_CACHE = None


def pm2_gateway_names_with_explicit_db_path() -> frozenset[str]:
    """Nombres `apps[].name` con ruta DuckDB explícita (``DUCKCLAW_*_DB_PATH`` o ``DUCKDB_PATH``)."""
    from duckclaw.gateway_db import raw_gateway_db_path_from_mapping

    global _NAMES_CACHE
    if _NAMES_CACHE is not None:
        return _NAMES_CACHE
    names: set[str] = set()
    cfg = _repo_root() / "config" / "api_gateways_pm2.json"
    try:
        raw = json.loads(cfg.read_text(encoding="utf-8"))
        apps = raw.get("apps") if isinstance(raw, dict) else None
        if isinstance(apps, list):
            for a in apps:
                if not isinstance(a, dict):
                    continue
                n = (a.get("name") or "").strip()
                env = a.get("env") if isinstance(a.get("env"), dict) else {}
                if n and raw_gateway_db_path_from_mapping(env):
                    names.add(n)
    except Exception:
        pass
    _NAMES_CACHE = frozenset(names)
    return _NAMES_CACHE


def dedicated_gateway_db_path_resolved() -> str | None:
    """
    Ruta absoluta del DuckDB dedicado del proceso gateway (misma que ``get_gateway_db_path()``).

    - Si el proceso está en ``api_gateways_pm2.json`` con rutas ``DUCKCLAW_*_DB_PATH``
      (nombre PM2 o match por puerto): el arranque ya volcó esas claves al entorno.
    - Sin bloque PM2 (``uvicorn`` local): None → multi-bóveda por usuario.

    ``_apply_db_path_from_api_gateways_pm2`` puede fijar ``DUCKCLAW_PM2_MATCHED_APP_NAME``
    por ``--port`` aunque el nombre PM2 real difiera; se acepta **cualquiera** de los
    dos si está en el JSON.
    """
    from duckclaw.gateway_db import get_gateway_db_path

    names = pm2_gateway_names_with_explicit_db_path()
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    matched = (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip()
    if not (proc in names or matched in names):
        return None
    resolved = get_gateway_db_path()
    if not (resolved or "").strip():
        return None
    return resolved
