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
    """Nombres `apps[].name` que declaran `env.DUCKCLAW_DB_PATH` no vacío."""
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
                dbp = (env.get("DUCKCLAW_DB_PATH") or "").strip()
                if n and dbp:
                    names.add(n)
    except Exception:
        pass
    _NAMES_CACHE = frozenset(names)
    return _NAMES_CACHE


def dedicated_gateway_db_path_resolved() -> str | None:
    """
    Ruta absoluta de DUCKCLAW_DB_PATH cuando el gateway debe usar una sola DuckDB
    (no el registry multi-bóveda por usuario).

    - Si el proceso está en ``api_gateways_pm2.json`` con ``DUCKCLAW_DB_PATH`` (nombre
      PM2 o match por puerto): se usa esa ruta.
    - Si hay ``DUCKCLAW_PM2_PROCESS_NAME`` pero **no** hay bloque en el JSON (p. ej.
      wizard creó ``JobHunter-Gateway`` sin editar el JSON): se usa igualmente
      ``DUCKCLAW_DB_PATH`` del entorno PM2/.env.
    - Sin nombre PM2 (p. ej. ``uvicorn`` local sin PM2): None → multi-bóveda.

    Importante: al arranque, ``_apply_db_path_from_api_gateways_pm2`` puede emparejar
    el bloque correcto por ``--port`` y fijar ``DUCKCLAW_PM2_MATCHED_APP_NAME`` a
    p. ej. ``BI-Analyst-Gateway`` aunque ``DUCKCLAW_PM2_PROCESS_NAME`` en PM2 lleve
    otro alias (p. ej. ``BIAnalyst-Gateway``). Hay que aceptar **cualquiera** de los
    dos si está en el JSON; si solo se mirara el nombre PM2, fly commands y el manager
    volverían al vault del registry (p. ej. finanzdb1) y chocarían por lock DuckDB.
    """
    gw_db = (os.environ.get("DUCKCLAW_DB_PATH") or "").strip()
    if not gw_db:
        return None
    resolved = str(Path(gw_db).expanduser().resolve())
    names = pm2_gateway_names_with_explicit_db_path()
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    matched = (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip()
    in_json = proc in names or matched in names
    if in_json:
        return resolved
    if proc:
        return resolved
    return None
